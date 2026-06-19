"""Configuration management for AMOS.

This module handles loading and accessing configuration from:
1. config.yaml file
2. Environment variables (override config.yaml)
3. Default values (fallback)

Usage:
    from amos.config import config
    
    # Access configuration
    host = config.server.host
    port = config.server.port
    
    # Check if feature is enabled
    if config.extraction.use_llm:
        # Use LLM extraction
        pass
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ServerConfig:
    """Server configuration."""
    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False
    workers: int = 1


@dataclass
class PostgresConfig:
    """PostgreSQL configuration."""
    dsn: str = "postgresql://amos:amos@localhost:5432/amos"
    pool_size: int = 10
    max_overflow: int = 20
    initialize: bool = True


@dataclass
class StorageConfig:
    """Storage configuration."""
    backend: str = "memory"
    postgres: PostgresConfig = field(default_factory=PostgresConfig)


@dataclass
class ExtractionConfig:
    """Extraction configuration."""
    use_llm: bool = False
    use_validation: bool = False
    llm_model: str = "phi"
    ollama_url: str = "http://localhost:11434"
    confidence_threshold: float = 0.6
    use_cascading: bool = False


@dataclass
class RetrievalWeights:
    """Retrieval scoring weights."""
    semantic: float = 0.40
    heat: float = 0.25
    recency: float = 0.15
    graph: float = 0.10
    diversity: float = 0.10


@dataclass
class RetrievalConfig:
    """Retrieval configuration."""
    default_limit: int = 10
    max_limit: int = 100
    weights: RetrievalWeights = field(default_factory=RetrievalWeights)


@dataclass
class EmbeddingsConfig:
    """Embeddings configuration."""
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 384
    device: str = "cpu"
    batch_size: int = 32


@dataclass
class HeatConfig:
    """Heat calculation configuration."""
    decay_lambda_per_day: float = 0.03
    importance_weight: float = 0.35
    frequency_weight: float = 0.25
    recency_weight: float = 0.20
    relationship_weight: float = 0.10
    confidence_weight: float = 0.10


@dataclass
class ThresholdsConfig:
    """Lifecycle thresholds configuration."""
    survivor_promotion: float = 0.65
    durable_promotion: float = 0.78
    survivor_archive: float = 0.18
    durable_demotion: float = 0.20
    archive_deletion: float = 0.05


@dataclass
class SchedulerConfig:
    """Scheduler configuration."""
    auto_gc: bool = True
    gc_interval: int = 3600


@dataclass
class LifecycleConfig:
    """Lifecycle configuration."""
    heat: HeatConfig = field(default_factory=HeatConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)


@dataclass
class AdmissionConfig:
    """Admission policy configuration."""
    threshold: float = 0.55
    type_weights: Dict[str, float] = field(default_factory=lambda: {
        "FACT": 0.18,
        "SKILL": 0.20,
        "PREFERENCE": 0.22,
        "BELIEF": 0.14,
        "RELATIONSHIP": 0.16,
        "SUMMARY": 0.18,
        "GOAL": 0.22,
        "TASK": 0.18,
        "EPISODE": 0.12,
        "OBSERVATION": 0.04,
    })


@dataclass
class ContextConfig:
    """Context compilation configuration."""
    default_budget: int = 2000
    max_budget: int = 8000
    tokens_per_char: float = 0.25


@dataclass
class AsyncProcessingConfig:
    """Async processing configuration."""
    enabled: bool = False
    workers: int = 1
    queue_size: int = 1000
    timeout: int = 30


@dataclass
class LogFileConfig:
    """Log file configuration."""
    enabled: bool = False
    path: str = "logs/amos.log"
    max_bytes: int = 10485760
    backup_count: int = 5


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: LogFileConfig = field(default_factory=LogFileConfig)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    enabled: bool = False
    requests_per_minute: int = 60


@dataclass
class AuthConfig:
    """Authentication configuration."""
    enabled: bool = False
    api_key: str = ""


@dataclass
class APIConfig:
    """API configuration."""
    cors_enabled: bool = True
    cors_origins: List[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://localhost:8080"
    ])
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)


@dataclass
class MCPConfig:
    """MCP server configuration."""
    name: str = "amos-memory"
    version: str = "2.0.0"
    debug: bool = False


@dataclass
class FeaturesConfig:
    """Feature flags configuration."""
    experimental: bool = False
    telemetry: bool = False
    profiling: bool = False


@dataclass
class DevelopmentConfig:
    """Development configuration."""
    auto_reload: bool = False
    detailed_errors: bool = True
    debug_endpoints: bool = False


@dataclass
class V3YoungGenerationConfig:
    """V3 Young generation configuration."""
    ttl_days: int = 7
    max_size: int = 500


@dataclass
class V3SurvivorSpaceConfig:
    """V3 Survivor space configuration."""
    max_size: int = 100


@dataclass
class V3PromotionWeights:
    """V3 Promotion scoring weights."""
    retrieval_frequency: float = 0.4
    mention_frequency: float = 0.2
    recency: float = 0.1
    importance: float = 0.1
    graph_connections: float = 0.2


@dataclass
class V3PromotionConfig:
    """V3 Promotion engine configuration."""
    threshold: float = 0.6
    check_interval: int = 300
    weights: V3PromotionWeights = field(default_factory=V3PromotionWeights)


@dataclass
class V3HeatConfig:
    """V3 Heat model configuration."""
    decay_daily: float = 0.98
    decay_weekly: float = 0.9
    min_threshold: float = 0.01


@dataclass
class V3ArchiveConfig:
    """V3 Archive configuration."""
    after_days: int = 90
    delete_after_days: int = 180


@dataclass
class V3ReflectionConfig:
    """V3 Reflection engine configuration."""
    enabled: bool = True
    model: str = "qwen2.5:3b"
    ollama_url: str = "http://localhost:11434"
    batch_size: int = 50
    check_interval: int = 3600
    min_episodes: int = 10
    min_confidence: float = 0.7


@dataclass
class V3Config:
    """V3 generational memory configuration."""
    enabled: bool = True
    young_generation: V3YoungGenerationConfig = field(default_factory=V3YoungGenerationConfig)
    survivor_space: V3SurvivorSpaceConfig = field(default_factory=V3SurvivorSpaceConfig)
    promotion: V3PromotionConfig = field(default_factory=V3PromotionConfig)
    heat: V3HeatConfig = field(default_factory=V3HeatConfig)
    archive: V3ArchiveConfig = field(default_factory=V3ArchiveConfig)
    reflection: V3ReflectionConfig = field(default_factory=V3ReflectionConfig)


@dataclass
class Config:
    """Main configuration class."""
    server: ServerConfig = field(default_factory=ServerConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    lifecycle: LifecycleConfig = field(default_factory=LifecycleConfig)
    admission: AdmissionConfig = field(default_factory=AdmissionConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    async_processing: AsyncProcessingConfig = field(default_factory=AsyncProcessingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    api: APIConfig = field(default_factory=APIConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)
    development: DevelopmentConfig = field(default_factory=DevelopmentConfig)
    v3: V3Config = field(default_factory=V3Config)


def load_config(config_path: str | None = None) -> Config:
    """Load configuration from file and environment variables.
    
    Args:
        config_path: Path to config.yaml file (default: ./config.yaml)
        
    Returns:
        Config object with loaded configuration
    """
    config = Config()
    
    # Try to load from YAML file
    if config_path is None:
        config_path = "config.yaml"
    
    config_file = Path(config_path)
    if config_file.exists():
        try:
            import yaml
            with open(config_file) as f:
                data = yaml.safe_load(f)
                if data:
                    _apply_dict_to_config(config, data)
        except ImportError:
            print("Warning: PyYAML not installed. Install with: pip install pyyaml")
        except Exception as e:
            print(f"Warning: Failed to load config file: {e}")
    
    # Override with environment variables
    _apply_env_vars(config)
    
    return config


def _apply_dict_to_config(config: Config, data: Dict[str, Any]) -> None:
    """Apply dictionary data to config object."""
    # Server
    if "server" in data:
        for key, value in data["server"].items():
            if hasattr(config.server, key):
                setattr(config.server, key, value)
    
    # Storage
    if "storage" in data:
        if "backend" in data["storage"]:
            config.storage.backend = data["storage"]["backend"]
        if "postgres" in data["storage"]:
            for key, value in data["storage"]["postgres"].items():
                if hasattr(config.storage.postgres, key):
                    setattr(config.storage.postgres, key, value)
    
    # Extraction
    if "extraction" in data:
        for key, value in data["extraction"].items():
            if hasattr(config.extraction, key):
                setattr(config.extraction, key, value)
    
    # Retrieval
    if "retrieval" in data:
        for key, value in data["retrieval"].items():
            if key == "weights" and isinstance(value, dict):
                for wkey, wvalue in value.items():
                    if hasattr(config.retrieval.weights, wkey):
                        setattr(config.retrieval.weights, wkey, wvalue)
            elif hasattr(config.retrieval, key):
                setattr(config.retrieval, key, value)

    if "embeddings" in data:
        _apply_attrs(config.embeddings, data["embeddings"])

    if "lifecycle" in data:
        lifecycle = data["lifecycle"]
        if "heat" in lifecycle:
            _apply_attrs(config.lifecycle.heat, lifecycle["heat"])
        if "thresholds" in lifecycle:
            _apply_attrs(config.lifecycle.thresholds, lifecycle["thresholds"])
        if "scheduler" in lifecycle:
            _apply_attrs(config.lifecycle.scheduler, lifecycle["scheduler"])

    if "admission" in data:
        for key, value in data["admission"].items():
            if hasattr(config.admission, key):
                setattr(config.admission, key, value)

    if "context" in data:
        _apply_attrs(config.context, data["context"])

    if "async_processing" in data:
        _apply_attrs(config.async_processing, data["async_processing"])

    if "logging" in data:
        for key, value in data["logging"].items():
            if key == "file" and isinstance(value, dict):
                _apply_attrs(config.logging.file, value)
            elif hasattr(config.logging, key):
                setattr(config.logging, key, value)

    if "api" in data:
        for key, value in data["api"].items():
            if key == "rate_limit" and isinstance(value, dict):
                _apply_attrs(config.api.rate_limit, value)
            elif key == "auth" and isinstance(value, dict):
                _apply_attrs(config.api.auth, value)
            elif hasattr(config.api, key):
                setattr(config.api, key, value)

    if "mcp" in data:
        _apply_attrs(config.mcp, data["mcp"])

    if "features" in data:
        _apply_attrs(config.features, data["features"])

    if "development" in data:
        _apply_attrs(config.development, data["development"])
    
    # V3 Configuration
    if "v3" in data:
        if "enabled" in data["v3"]:
            config.v3.enabled = data["v3"]["enabled"]
        
        if "young_generation" in data["v3"]:
            for key, value in data["v3"]["young_generation"].items():
                if hasattr(config.v3.young_generation, key):
                    setattr(config.v3.young_generation, key, value)
        
        if "survivor_space" in data["v3"]:
            for key, value in data["v3"]["survivor_space"].items():
                if hasattr(config.v3.survivor_space, key):
                    setattr(config.v3.survivor_space, key, value)
        
        if "promotion" in data["v3"]:
            for key, value in data["v3"]["promotion"].items():
                if key == "weights" and isinstance(value, dict):
                    for wkey, wvalue in value.items():
                        if hasattr(config.v3.promotion.weights, wkey):
                            setattr(config.v3.promotion.weights, wkey, wvalue)
                elif hasattr(config.v3.promotion, key):
                    setattr(config.v3.promotion, key, value)
        
        if "heat" in data["v3"]:
            for key, value in data["v3"]["heat"].items():
                if hasattr(config.v3.heat, key):
                    setattr(config.v3.heat, key, value)
        
        if "archive" in data["v3"]:
            for key, value in data["v3"]["archive"].items():
                if hasattr(config.v3.archive, key):
                    setattr(config.v3.archive, key, value)
        
        if "reflection" in data["v3"]:
            for key, value in data["v3"]["reflection"].items():
                if hasattr(config.v3.reflection, key):
                    setattr(config.v3.reflection, key, value)


def _apply_attrs(target: Any, values: Dict[str, Any]) -> None:
    for key, value in values.items():
        if hasattr(target, key):
            setattr(target, key, value)


def _apply_env_vars(config: Config) -> None:
    """Apply environment variable overrides."""
    # Server
    if host := os.getenv("AMOS_HOST"):
        config.server.host = host
    if port := os.getenv("AMOS_PORT"):
        config.server.port = int(port)
    
    # Storage
    if backend := os.getenv("AMOS_STORAGE_BACKEND"):
        config.storage.backend = backend
    if dsn := os.getenv("AMOS_POSTGRES_DSN"):
        config.storage.postgres.dsn = dsn
    
    # Extraction
    if use_llm := os.getenv("AMOS_USE_LLM"):
        config.extraction.use_llm = use_llm.lower() == "true"
    if use_validation := os.getenv("AMOS_USE_VALIDATION"):
        config.extraction.use_validation = use_validation.lower() == "true"
    if use_cascading := os.getenv("AMOS_USE_CASCADING"):
        config.extraction.use_cascading = use_cascading.lower() == "true"
    if model := os.getenv("AMOS_LLM_MODEL"):
        config.extraction.llm_model = model
    if url := os.getenv("AMOS_OLLAMA_URL"):
        config.extraction.ollama_url = url
    if threshold := os.getenv("AMOS_EXTRACTION_CONFIDENCE_THRESHOLD"):
        config.extraction.confidence_threshold = float(threshold)

    # Embeddings
    if embedding_model := os.getenv("AMOS_EMBEDDING_MODEL"):
        config.embeddings.model = embedding_model

    # Lifecycle
    if heat_decay := os.getenv("AMOS_HEAT_DECAY_LAMBDA_PER_DAY"):
        config.lifecycle.heat.decay_lambda_per_day = float(heat_decay)
    if survivor_promotion := os.getenv("AMOS_SURVIVOR_PROMOTION_THRESHOLD"):
        config.lifecycle.thresholds.survivor_promotion = float(survivor_promotion)
    if durable_promotion := os.getenv("AMOS_DURABLE_PROMOTION_THRESHOLD"):
        config.lifecycle.thresholds.durable_promotion = float(durable_promotion)
    if archive_threshold := os.getenv("AMOS_ARCHIVE_THRESHOLD"):
        config.lifecycle.thresholds.survivor_archive = float(archive_threshold)
    if delete_threshold := os.getenv("AMOS_ARCHIVE_DELETE_THRESHOLD"):
        config.lifecycle.thresholds.archive_deletion = float(delete_threshold)

    # Async processing
    if async_enabled := os.getenv("AMOS_ASYNC_PROCESSING"):
        config.async_processing.enabled = async_enabled.lower() == "true"
    if async_workers := os.getenv("AMOS_ASYNC_WORKERS"):
        config.async_processing.workers = int(async_workers)
    
    # API
    if api_key := os.getenv("AMOS_API_KEY"):
        config.api.auth.api_key = api_key
        config.api.auth.enabled = True


# Global config instance
config = load_config()
