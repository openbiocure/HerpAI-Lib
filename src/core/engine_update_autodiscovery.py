from typing import TypeVar, Type, Dict, Any, Optional, Set, List, Callable
from .dependency import IServiceScope, IEngine
from .startup import StartupTaskExecutor, IStartupTask
from ..data.db_context import DbContext, IDbContext
from ..config.yaml_config import YamlConfig
import inspect
import pkgutil
import importlib
import sys
import logging

logger = logging.getLogger(__name__)
T = TypeVar('T')

class Singleton:
    _instances = {}
    
    @classmethod
    def get_instance(cls, class_type: Type[T]) -> T:
        if class_type not in cls._instances:
            cls._instances[class_type] = class_type()
        return cls._instances[class_type]

class ServiceCollection:
    def __init__(self):
        self._services = {}
        self._scoped_factories = {}
        self._transient_factories = {}
    
    def add_singleton(self, interface_type: Type[T], implementation):
        """Register a singleton service."""
        if callable(implementation) and not isinstance(implementation, type):
            # Factory function
            instance = implementation()
            self._services[interface_type] = instance
        else:
            # Type or instance
            if isinstance(implementation, type):
                instance = implementation()
            else:
                instance = implementation
            self._services[interface_type] = instance
    
    def add_scoped(self, interface_type: Type[T], implementation_factory):
        """Register a scoped service factory."""
        if isinstance(implementation_factory, type):
            factory = implementation_factory
        else:
            factory = implementation_factory
        self._scoped_factories[interface_type] = factory
    
    def add_transient(self, interface_type: Type[T], implementation_factory):
        """Register a transient service factory."""
        if isinstance(implementation_factory, type):
            factory = implementation_factory
        else:
            factory = implementation_factory
        self._transient_factories[interface_type] = factory
    
    def get_service(self, service_type: Type[T]) -> Optional[T]:
        """Get a registered service."""
        service = self._services.get(service_type)
        if service is not None:
            return service
        
        # If it's a scoped service, we need a scope
        if service_type in self._scoped_factories:
            raise ValueError(f"Service {service_type.__name__} is scoped and requires a ServiceScope")
        
        # If it's a transient service, create a new instance
        if service_type in self._transient_factories:
            factory = self._transient_factories[service_type]
            if inspect.isclass(factory):
                return factory()
            else:
                return factory()
        
        return None

class ServiceScope(IServiceScope):
    def __init__(self, engine: 'Engine'):
        self._engine = engine
        self._scoped_services = {}
    
    def resolve(self, type_: Type[T]) -> T:
        # Check if we have the service in this scope
        service = self._scoped_services.get(type_)
        if service is not None:
            return service
        
        # Check if it's a scoped service
        factory = self._engine._services._scoped_factories.get(type_)
        if factory is not None:
            if inspect.isclass(factory):
                service = factory()
            else:
                service = factory()
            self._scoped_services[type_] = service
            return service
        
        # Otherwise, delegate to the engine
        return self._engine.resolve(type_)
    
    async def dispose(self) -> None:
        # Clean up resources
        for service in self._scoped_services.values():
            if hasattr(service, 'dispose') and callable(service.dispose):
                await service.dispose()
        self._scoped_services.clear()

class Engine(IEngine):
    _instance: Optional['Engine'] = None
    
    def __init__(self):
        self._services = ServiceCollection()
        self._started = False
        self._modules = set()
        self._startup_task_executor = None
    
    @classmethod
    def initialize(cls) -> 'Engine':
        return Singleton.get_instance(cls)
    
    @property
    def current(self) -> 'IEngine':
        return self
    
    def start(self) -> None:
        if self._started:
            return
        
        logger.info("Starting engine...")
        
        # Discover and execute startup tasks
        self._startup_task_executor = StartupTaskExecutor.discover_tasks()
        
        # Get configuration to configure tasks
        try:
            config = YamlConfig.get_instance()
            self._startup_task_executor.configure_tasks(config._config)
        except Exception as e:
            logger.warning(f"Failed to configure startup tasks from config: {str(e)}")
        
        # Execute startup tasks
        self._startup_task_executor.execute_all()
        
        # Register core services
        self._register_core_services()
        
        self._started = True
        logger.info("Engine started successfully")
    
    def resolve(self, type_: Type[T]) -> T:
        if not self._started:
            raise RuntimeError("Engine not started. Call start() first.")
        
        service = self._services.get_service(type_)
        if service is None:
            raise ValueError(f"No registration found for {type_.__name__}")
        return service
    
    def create_scope(self) -> IServiceScope:
        return ServiceScope(self)
    
    def register(self, interface_type: Type[T], implementation) -> None:
        """Register a singleton service."""
        self._services.add_singleton(interface_type, implementation)
    
    def add_startup_task(self, task: IStartupTask) -> None:
        """
        Add a startup task to be executed when the engine starts.
        
        Note: This method is not typically needed as startup tasks are auto-discovered.
        Use it only if you need to add a task dynamically.
        """
        if self._startup_task_executor is None:
            self._startup_task_executor = StartupTaskExecutor()
        self._startup_task_executor.add_task(task)
    
    def _register_core_services(self):
        """Register core services required by the library."""
        # Register self
        self._services.add_singleton(IEngine, self)
        self._services.add_singleton(Engine, self)
        
        # Register configuration
        config = YamlConfig.get_instance()
        self._services.add_singleton(YamlConfig, config)
        
        # Setup database using configuration
        self._services.add_singleton(IDbContext, lambda: DbContext())
        self._services.add_singleton(DbContext, lambda: self.resolve(IDbContext))
        
        # Auto-discover and register repositories
        self._discover_and_register_entities()
    
    def _discover_and_register_entities(self):
        """Discover entity types and register repositories for them."""
        # This would scan packages and modules to find entity types
        # Then register appropriate repositories
        # Simplified implementation
        pass
