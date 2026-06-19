from __future__ import annotations

from .config import load_config
from .embeddings import build_embeddings
from .engines.adaptive_scheduler import ThresholdConfig
from .engines.heat import HeatEngine
from .service import Amos


def build_amos(
    *,
    use_cascading_extraction: bool | None = None,
    use_tiny_llm: bool | None = None,
    enable_async_processing: bool | None = None,
    async_workers: int | None = None,
    use_adaptive_scheduler: bool = True,  # Enabled by default for better lifecycle management
) -> Amos:
    """Build AMOS instance with configuration from config.yaml and environment.
    
    Configuration is loaded from (in order of precedence):
    1. Function parameters (if provided)
    2. Environment variables (AMOS_*)
    3. config.yaml file
    4. Default values
    
    Args:
        use_cascading_extraction: Enable cascading extraction (default: from config)
        use_tiny_llm: Enable LLM for extraction (default: from config)
        enable_async_processing: Enable async background processing (default: from config)
        async_workers: Number of async worker threads (default: from config)
        use_adaptive_scheduler: Enable adaptive threshold optimization (default: True)
        
    Returns:
        Configured AMOS instance
        
    Example:
        # Use config.yaml settings with adaptive scheduler
        amos = build_amos()
        
        # Override specific settings
        amos = build_amos(use_tiny_llm=True, use_adaptive_scheduler=False)
    """
    config = load_config()

    # Use config values if not explicitly provided
    if use_cascading_extraction is None:
        use_cascading_extraction = config.extraction.use_cascading
    if use_tiny_llm is None:
        use_tiny_llm = config.extraction.use_llm
    if enable_async_processing is None:
        enable_async_processing = config.async_processing.enabled
    if async_workers is None:
        async_workers = config.async_processing.workers
    
    backend = config.storage.backend.lower()
    heat = HeatEngine(
        decay_lambda_per_day=config.lifecycle.heat.decay_lambda_per_day,
        importance_weight=config.lifecycle.heat.importance_weight,
        frequency_weight=config.lifecycle.heat.frequency_weight,
        recency_weight=config.lifecycle.heat.recency_weight,
        relationship_weight=config.lifecycle.heat.relationship_weight,
        confidence_weight=config.lifecycle.heat.confidence_weight,
    )
    adaptive_thresholds = ThresholdConfig(
        active_to_survivor=config.lifecycle.thresholds.survivor_promotion,
        survivor_to_durable=config.lifecycle.thresholds.durable_promotion,
        archive_threshold=config.lifecycle.thresholds.survivor_archive,
        delete_threshold=config.lifecycle.thresholds.archive_deletion,
    )
    retrieval_weights = {
        "semantic_weight": config.retrieval.weights.semantic,
        "heat_weight": config.retrieval.weights.heat,
        "recency_weight": config.retrieval.weights.recency,
        "graph_weight": config.retrieval.weights.graph,
        "diversity_weight": config.retrieval.weights.diversity,
    }
    service_kwargs = {
        "use_cascading_extraction": use_cascading_extraction,
        "use_tiny_llm": use_tiny_llm,
        "extraction_use_validation": config.extraction.use_validation,
        "extraction_llm_model": config.extraction.llm_model,
        "extraction_ollama_url": config.extraction.ollama_url,
        "extraction_confidence_threshold": config.extraction.confidence_threshold,
        "enable_async_processing": enable_async_processing,
        "async_workers": async_workers,
        "use_adaptive_scheduler": use_adaptive_scheduler,
        "heat": heat,
        "adaptive_thresholds": adaptive_thresholds,
        "admission_threshold": config.admission.threshold,
        "admission_type_weights": config.admission.type_weights,
        "retrieval_weights": retrieval_weights,
    }
    
    if backend == "memory":
        return Amos(**service_kwargs)
    
    if backend == "postgres":
        from .stores.postgres import PostgresStorage

        postgres = PostgresStorage(
            dsn=config.storage.postgres.dsn,
            initialize=config.storage.postgres.initialize,
            embedding_model=build_embeddings(config.embeddings.model),
        )
        return Amos(
            memories=postgres,
            timeline=postgres,
            graph=postgres,
            events=postgres,
            **service_kwargs,
        )
    
    raise ValueError(f"unsupported storage backend: {backend} (supported: memory, postgres)")
