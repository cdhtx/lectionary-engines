"""
Entry point for running the web application
"""

if __name__ == "__main__":
    import uvicorn
    from .config import WebConfig

    config = WebConfig.load()

    print("=" * 60)
    print("Lectionary Engines - Web Application")
    print("=" * 60)

    uvicorn.run(
        "web.app:app",
        host=config.web_host,
        port=config.web_port,
        reload=True
    )
