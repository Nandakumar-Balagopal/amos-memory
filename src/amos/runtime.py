from __future__ import annotations

from .config import config
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
    
    if backend == "memory":
        return Amos(
            use_cascading_extraction=use_cascading_extraction,
            use_tiny_llm=use_tiny_llm,
            enable_async_processing=enable_async_processing,
            async_workers=async_workers,
            use_adaptive_scheduler=use_adaptive_scheduler,
        )
    
    if backend == "postgres":
        from .stores.postgres import PostgresStorage

        postgres = PostgresStorage(
            dsn=config.storage.postgres.dsn,
            initialize=config.storage.postgres.initialize,
        )
        return Amos(
            memories=postgres,
            timeline=postgres,
            graph=postgres,
            events=postgres,
            use_cascading_extraction=use_cascading_extraction,
            use_tiny_llm=use_tiny_llm,
            enable_async_processing=enable_async_processing,
            async_workers=async_workers,
            use_adaptive_scheduler=use_adaptive_scheduler,
        )
    
    raise ValueError(f"unsupported storage backend: {backend} (supported: memory, postgres)")

