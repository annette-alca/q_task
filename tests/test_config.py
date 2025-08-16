import pytest
from app.config import config

class TestConfig:
    """Test configuration loading from environment variables"""
    
    def test_postgres_config(self):
        """Test PostgreSQL configuration values"""
        assert isinstance(config.POSTGRES_HOST, str)
        assert isinstance(config.POSTGRES_PORT, int)
        assert isinstance(config.POSTGRES_USER, str)
        assert isinstance(config.POSTGRES_PASSWORD, str)
        assert isinstance(config.POSTGRES_DATABASE, str)
        
        # Verify default values if not set
        assert config.POSTGRES_HOST in ["localhost", "127.0.0.1"]
        assert config.POSTGRES_PORT in [5432, 5433]  # Allow both default and docker port
        assert config.POSTGRES_DATABASE == "trading"
    
    def test_redis_config(self):
        """Test Redis configuration values"""
        assert isinstance(config.REDIS_HOST, str)
        assert isinstance(config.REDIS_PORT, int)
        assert isinstance(config.REDIS_DB, int)
        
        # Verify default values if not set
        assert config.REDIS_HOST in ["localhost", "127.0.0.1"]
        assert config.REDIS_PORT == 6379
        assert config.REDIS_DB == 0
    
    def test_app_config(self):
        """Test application configuration values"""
        assert isinstance(config.APP_NAME, str)
        assert isinstance(config.APP_VERSION, str)
        assert isinstance(config.DEBUG, bool)
        
        # Verify default values if not set
        assert len(config.APP_NAME) > 0
        assert len(config.APP_VERSION) > 0
    
    def test_server_config(self):
        """Test server configuration values"""
        assert isinstance(config.HOST, str)
        assert isinstance(config.PORT, int)
        
        # Verify default values if not set
        assert config.HOST in ["0.0.0.0", "localhost", "127.0.0.1"]
        assert config.PORT == 8000
    
    def test_debug_boolean_conversion(self):
        """Test that DEBUG is properly converted to boolean"""
        assert isinstance(config.DEBUG, bool)
