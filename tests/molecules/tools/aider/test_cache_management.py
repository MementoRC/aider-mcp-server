import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aider_mcp_server.molecules.tools.aider.cache_management import CacheManager


class TestCacheManager:
    """Test suite for CacheManager class."""

    @pytest.fixture
    def cache_manager(self):
        """Create a fresh CacheManager instance for each test."""
        return CacheManager()

    @pytest.fixture
    def mock_diff_cache(self):
        """Create a mock DiffCache instance."""
        mock_cache = AsyncMock()
        mock_cache.start = AsyncMock()
        mock_cache.shutdown = AsyncMock()
        mock_cache.compare_and_cache = AsyncMock()
        mock_cache.get = AsyncMock()
        mock_cache.get_stats = MagicMock(return_value={
            'hits': 5,
            'misses': 3,
            'total_accesses': 8,
            'current_size': 1024,
            'max_size': 10240,
            'hit_rate': 0.625
        })
        return mock_cache

    # Cache Lifecycle Tests

    @pytest.mark.asyncio
    async def test_initialize_cache_success(self, cache_manager, mock_diff_cache):
        """Test successful cache initialization."""
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            await cache_manager.initialize_cache()
            
            assert cache_manager.diff_cache is not None
            assert cache_manager._diff_cache == mock_diff_cache
            mock_diff_cache.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_cache_already_initialized(self, cache_manager, mock_diff_cache):
        """Test double initialization handling."""
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            # Initialize once
            await cache_manager.initialize_cache()
            mock_diff_cache.start.assert_called_once()
            
            # Reset mock to verify second call behavior
            mock_diff_cache.start.reset_mock()
            
            # Initialize again - should not create new instance
            await cache_manager.initialize_cache()
            mock_diff_cache.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_cache_success(self, cache_manager, mock_diff_cache):
        """Test successful cache shutdown."""
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            # Initialize first
            await cache_manager.initialize_cache()
            assert cache_manager.diff_cache is not None
            
            # Shutdown
            await cache_manager.shutdown_cache()
            assert cache_manager.diff_cache is None
            mock_diff_cache.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_cache_not_initialized(self, cache_manager):
        """Test shutdown when cache is not initialized."""
        # Should not raise exception
        await cache_manager.shutdown_cache()
        assert cache_manager.diff_cache is None

    def test_diff_cache_property_access(self, cache_manager):
        """Test diff_cache property access."""
        # Initially None
        assert cache_manager.diff_cache is None
        
        # Set manually for testing
        mock_cache = MagicMock()
        cache_manager._diff_cache = mock_cache
        assert cache_manager.diff_cache == mock_cache

    # Cache Key Generation Tests

    def test_generate_cache_key_basic(self, cache_manager):
        """Test basic cache key generation."""
        working_dir = "/test/dir"
        files = ["file1.py", "file2.py"]
        
        key = cache_manager.generate_cache_key(working_dir, files)
        
        assert isinstance(key, str)
        assert key.startswith("diffcache:")
        assert len(key) > 10  # Should be a meaningful hash

    def test_generate_cache_key_consistency(self, cache_manager):
        """Test that same inputs produce same key."""
        working_dir = "/test/dir"
        files = ["file1.py", "file2.py"]
        
        key1 = cache_manager.generate_cache_key(working_dir, files)
        key2 = cache_manager.generate_cache_key(working_dir, files)
        
        assert key1 == key2

    def test_generate_cache_key_uniqueness(self, cache_manager):
        """Test that different inputs produce different keys."""
        key1 = cache_manager.generate_cache_key("/test/dir", ["file1.py"])
        key2 = cache_manager.generate_cache_key("/test/dir", ["file2.py"])
        key3 = cache_manager.generate_cache_key("/other/dir", ["file1.py"])
        
        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_generate_cache_key_with_none_working_dir(self, cache_manager):
        """Test cache key generation with None working directory."""
        files = ["file1.py", "file2.py"]
        
        key = cache_manager.generate_cache_key(None, files)
        
        assert isinstance(key, str)
        assert key.startswith("diffcache:")

    def test_generate_cache_key_with_empty_files(self, cache_manager):
        """Test cache key generation with empty file list."""
        working_dir = "/test/dir"
        files = []
        
        key = cache_manager.generate_cache_key(working_dir, files)
        
        assert isinstance(key, str)
        assert key.startswith("diffcache:")

    def test_generate_cache_key_file_order_independence(self, cache_manager):
        """Test that file order doesn't affect cache key."""
        working_dir = "/test/dir"
        files1 = ["file1.py", "file2.py", "file3.py"]
        files2 = ["file3.py", "file1.py", "file2.py"]
        
        key1 = cache_manager.generate_cache_key(working_dir, files1)
        key2 = cache_manager.generate_cache_key(working_dir, files2)
        
        assert key1 == key2

    # Diff Cache Processing Tests

    @pytest.mark.asyncio
    async def test_process_diff_cache_disabled(self, cache_manager):
        """Test diff processing with cache disabled."""
        cache_key = "test_key"
        raw_diff = "test diff content"
        
        result_diff, is_cached = await cache_manager.process_diff_cache(
            cache_key, raw_diff, use_diff_cache=False
        )
        
        assert result_diff == raw_diff
        assert is_cached is False

    @pytest.mark.asyncio
    async def test_process_diff_cache_not_initialized(self, cache_manager):
        """Test diff processing when cache is not initialized."""
        cache_key = "test_key"
        raw_diff = "test diff content"
        
        result_diff, is_cached = await cache_manager.process_diff_cache(
            cache_key, raw_diff, use_diff_cache=True
        )
        
        assert result_diff == raw_diff
        assert is_cached is False

    @pytest.mark.asyncio
    async def test_process_diff_cache_with_changes(self, cache_manager, mock_diff_cache):
        """Test diff processing when cache detects changes."""
        cache_key = "test_key"
        raw_diff = "test diff content"
        
        # Mock cache to return changes
        mock_diff_cache.compare_and_cache.return_value = {"diff": "new changes"}
        
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            await cache_manager.initialize_cache()
            
            result_diff, is_cached = await cache_manager.process_diff_cache(
                cache_key, raw_diff, use_diff_cache=True
            )
            
            assert result_diff == '{"diff": "new changes"}'
            assert is_cached is False
            mock_diff_cache.compare_and_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_diff_cache_no_changes_with_cached_content(self, cache_manager, mock_diff_cache):
        """Test diff processing when no changes and cached content exists."""
        cache_key = "test_key"
        raw_diff = "test diff content"
        
        # Mock cache to return no changes but have cached content
        mock_diff_cache.compare_and_cache.return_value = None
        mock_diff_cache.get.return_value = {"diff": "cached content"}
        
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            await cache_manager.initialize_cache()
            
            result_diff, is_cached = await cache_manager.process_diff_cache(
                cache_key, raw_diff, use_diff_cache=True
            )
            
            assert result_diff == '{"diff": "cached content"}'
            assert is_cached is True
            mock_diff_cache.get.assert_called_once_with(cache_key)

    @pytest.mark.asyncio
    async def test_process_diff_cache_no_changes_no_cached_content(self, cache_manager, mock_diff_cache):
        """Test diff processing when no changes and no cached content."""
        cache_key = "test_key"
        raw_diff = "test diff content"
        
        # Mock cache to return no changes and no cached content
        mock_diff_cache.compare_and_cache.return_value = None
        mock_diff_cache.get.return_value = None
        
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            await cache_manager.initialize_cache()
            
            result_diff, is_cached = await cache_manager.process_diff_cache(
                cache_key, raw_diff, use_diff_cache=True
            )
            
            assert result_diff == ""
            assert is_cached is True

    @pytest.mark.asyncio
    async def test_process_diff_cache_clear_cached_for_unchanged(self, cache_manager, mock_diff_cache):
        """Test clear_cached_for_unchanged parameter behavior."""
        cache_key = "test_key"
        raw_diff = "test diff content"
        
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            await cache_manager.initialize_cache()
            
            await cache_manager.process_diff_cache(
                cache_key, raw_diff, use_diff_cache=True, clear_cached_for_unchanged=True
            )
            
            # Verify the parameter was passed to compare_and_cache
            mock_diff_cache.compare_and_cache.assert_called_once_with(
                cache_key, {"diff": raw_diff}, clear_cached_for_unchanged=True
            )

    @pytest.mark.asyncio
    async def test_process_diff_cache_with_json_diff(self, cache_manager, mock_diff_cache):
        """Test diff processing with JSON-formatted diff input."""
        cache_key = "test_key"
        raw_diff = '{"files": ["test.py"], "changes": "some changes"}'
        
        mock_diff_cache.compare_and_cache.return_value = {"files": ["test.py"], "changes": "some changes"}
        
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            await cache_manager.initialize_cache()
            
            result_diff, is_cached = await cache_manager.process_diff_cache(
                cache_key, raw_diff, use_diff_cache=True
            )
            
            # Should parse JSON and pass parsed object to cache
            expected_diff_obj = {"files": ["test.py"], "changes": "some changes"}
            mock_diff_cache.compare_and_cache.assert_called_once_with(
                cache_key, expected_diff_obj, clear_cached_for_unchanged=True
            )

    @pytest.mark.asyncio
    async def test_process_diff_cache_error_handling(self, cache_manager, mock_diff_cache):
        """Test error handling during cache operations."""
        cache_key = "test_key"
        raw_diff = "test diff content"
        
        # Mock cache to raise exception
        mock_diff_cache.compare_and_cache.side_effect = Exception("Cache error")
        
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            await cache_manager.initialize_cache()
            
            result_diff, is_cached = await cache_manager.process_diff_cache(
                cache_key, raw_diff, use_diff_cache=True
            )
            
            # Should fallback to raw diff on error
            assert result_diff == raw_diff
            assert is_cached is False

    # Statistics Tests

    def test_get_cache_statistics_with_initialized_cache(self, cache_manager, mock_diff_cache):
        """Test getting statistics when cache is initialized."""
        expected_stats = {
            'hits': 5,
            'misses': 3,
            'total_accesses': 8,
            'current_size': 1024,
            'max_size': 10240,
            'hit_rate': 0.625
        }
        
        cache_manager._diff_cache = mock_diff_cache
        
        stats = cache_manager.get_cache_statistics()
        
        assert stats == expected_stats
        mock_diff_cache.get_stats.assert_called_once()

    def test_get_cache_statistics_without_initialized_cache(self, cache_manager):
        """Test getting statistics when cache is not initialized."""
        stats = cache_manager.get_cache_statistics()
        
        assert stats == {}

    # Integration Tests

    @pytest.mark.asyncio
    async def test_full_workflow(self, cache_manager, mock_diff_cache):
        """Test complete workflow from initialization through processing to shutdown."""
        raw_diff = "integration test diff"
        
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            # Initialize cache
            await cache_manager.initialize_cache()
            assert cache_manager.diff_cache is not None
            
            # Generate cache key
            working_dir = "/test/integration"
            files = ["file1.py", "file2.py"]
            key = cache_manager.generate_cache_key(working_dir, files)
            assert key.startswith("diffcache:")
            
            # Process diff
            mock_diff_cache.compare_and_cache.return_value = {"diff": "processed changes"}
            result_diff, is_cached = await cache_manager.process_diff_cache(
                key, raw_diff, use_diff_cache=True
            )
            assert '"diff": "processed changes"' in result_diff
            assert is_cached is False
            
            # Get statistics
            stats = cache_manager.get_cache_statistics()
            assert 'hits' in stats
            
            # Shutdown cache
            await cache_manager.shutdown_cache()
            assert cache_manager.diff_cache is None

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, cache_manager, mock_diff_cache):
        """Test concurrent cache operations."""
        with patch('aider_mcp_server.molecules.tools.aider.cache_management.DiffCache', return_value=mock_diff_cache):
            # Test concurrent initialization (should be thread-safe)
            tasks = [cache_manager.initialize_cache() for _ in range(5)]
            await asyncio.gather(*tasks)
            
            # Should only have one cache instance
            assert cache_manager.diff_cache == mock_diff_cache
            # Start should be called at least once (lock prevents multiple calls)
            assert mock_diff_cache.start.call_count >= 1
            
            # Test concurrent shutdown
            tasks = [cache_manager.shutdown_cache() for _ in range(3)]
            await asyncio.gather(*tasks)
            
            assert cache_manager.diff_cache is None