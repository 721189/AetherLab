"""Object storage integration tests.

Tests the local filesystem backend (the default when no S3 endpoint is
configured). The S3 backend is exercised only when boto3 is installed and
OBJECT_STORE_* settings are provided; those paths are opt-in.
"""

from __future__ import annotations

import hashlib
import pytest

from app.services.storage import (
    ObjectStoreDisabledError,
    ObjectStoreError,
    ObjectStoreService,
    _LocalStore,
    satellite_product_key,
)


# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------

class TestSatelliteProductKey:
    def test_basic(self):
        key = satellite_product_key(
            source="sentinel2",
            scene_id="S2A_MSIL1C_20260801T045621_N0510_R094_T30TVK_20260801T064955",
            sub_key="B04",
            ext="tif",
        )
        assert key.startswith("satellite_products/sentinel2/")
        assert "S2A_MSIL1C_20260801T04562" in key
        assert key.endswith("/B04.tif")

    def test_no_sub_key(self):
        key = satellite_product_key(
            source="sentinel5p",
            scene_id="S5P_TROPOMI_20260801T000000",
            ext="nc",
        )
        assert key.endswith(".nc")
        assert "/S5P_TROPOMI_20260801T000000/" in key

    def test_sanitised_source(self):
        key = satellite_product_key(source="SENTINEL-2  ", scene_id="sc1", ext="tif")
        assert key.startswith("satellite_products/sentinel-2_")

    def test_sanitised_scene_id(self):
        key = satellite_product_key(source="s1", scene_id="a/b/c.txt", ext="tif")
        assert ".." not in key
        assert "/" not in key.split("/")[-2]

    def test_sanitised_sub_key(self):
        key = satellite_product_key(source="s1", scene_id="sc1", sub_key="my file v2", ext="tif")
        assert key.endswith("/my_file_v2.tif")


# ---------------------------------------------------------------------------
# Local filesystem backend
# ---------------------------------------------------------------------------

class TestLocalStore:
    @pytest.fixture
    def store(self, tmp_path):
        return _LocalStore(root=str(tmp_path))

    def test_put_get(self, store):
        key = "satellite_products/sentinel2/sc1/B04.tif"
        data = b"\x00\x01\x02hello"
        assert store.put(key, data) == key
        assert store.get(key) == data

    def test_get_missing_raises(self, store):
        with pytest.raises(FileNotFoundError):
            store.get("satellite_products/ghost.tif")

    def test_exists(self, store):
        store.put("satellite_products/x.tif", b"data")
        assert store.exists("satellite_products/x.tif")
        assert not store.exists("satellite_products/missing.tif")

    def test_delete(self, store):
        key = "satellite_products/del.tif"
        store.put(key, b"gone")
        store.delete(key)
        assert not store.exists(key)

    def test_list(self, store):
        store.put("satellite_products/sentinel2/sc1/B04.tif", b"r")
        store.put("satellite_products/sentinel2/sc1/B08.tif", b"n")
        store.put("satellite_products/sentinel5p/sc2/v1.tif", b"p")
        keys = store.list()
        assert "satellite_products/sentinel2/sc1/B04.tif" in keys
        assert "satellite_products/sentinel2/sc1/B08.tif" in keys
        assert "satellite_products/sentinel5p/sc2/v1.tif" in keys
        assert len(keys) == 3

    def test_list_with_prefix(self, store):
        store.put("satellite_products/sentinel2/sc1/B04.tif", b"r")
        store.put("satellite_products/sentinel5p/sc2/v1.tif", b"p")
        keys = store.list(prefix="satellite_products/sentinel2/")
        assert len(keys) == 1
        assert keys[0].endswith("B04.tif")

    def test_checksum(self, store):
        key = "satellite_products/chk.tif"
        store.put(key, b"\x01\x02\x03")
        assert store.checksum(key) == "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"

    def test_presigned_url(self, tmp_path):
        store = _LocalStore(root=str(tmp_path))
        key = "satellite_products/url.tif"
        store.put(key, b"viewable")
        url = store.presigned_download_url(key)
        assert url is not None
        assert url.startswith("file://")
        assert "url.tif" in url

    def test_presigned_url_missing(self, store):
        assert store.presigned_download_url("satellite_products/ghost.tif") is None

    def test_nested_folders_created(self, store):
        key = "satellite_products/deeply/nested/folder/file.tif"
        store.put(key, b"nested")
        assert store.exists(key)

    def test_overwrite_allowed(self, store):
        key = "satellite_products/ov.tif"
        store.put(key, b"v1")
        store.put(key, b"v2")
        assert store.get(key) == b"v2"

"""Object storage integration tests.

Tests the local filesystem backend (the default when no S3 endpoint is
configured). The S3 backend is exercised only when boto3 is installed and
OBJECT_STORE_* settings are provided; those paths are opt-in.
"""

from __future__ import annotations

import pytest

from app.services.storage import (
    ObjectStoreDisabledError,
    ObjectStoreError,
    ObjectStoreService,
    _LocalStore,
    satellite_product_key,
)


# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------

class TestSatelliteProductKey:
    def test_basic(self):
        key = satellite_product_key(
            source="sentinel2",
            scene_id="S2A_MSIL1C_20260801T045621_N0510_R094_T30TVK_20260801T064955",
            sub_key="B04",
            ext="tif",
        )
        assert key.startswith("satellite_products/sentinel2/")
        assert "S2A_MSIL1C_20260801T04562" in key
        assert key.endswith("/B04.tif")

    def test_no_sub_key(self):
        key = satellite_product_key(
            source="sentinel5p",
            scene_id="S5P_TROPOMI_20260801T000000",
            ext="nc",
        )
        assert key.endswith(".nc")
        assert "/S5P_TROPOMI_20260801T000000/" in key

    def test_sanitised_source(self):
        key = satellite_product_key(source="SENTINEL-2  ", scene_id="sc1", ext="tif")
        assert key.startswith("satellite_products/sentinel-2_")

    def test_sanitised_scene_id(self):
        key = satellite_product_key(source="s1", scene_id="a/b/c.txt", ext="tif")
        assert ".." not in key
        assert "/" not in key.split("/")[-2]

    def test_sanitised_sub_key(self):
        key = satellite_product_key(source="s1", scene_id="sc1", sub_key="my file v2", ext="tif")
        assert key.endswith("/my_file_v2.tif")


class TestLocalStore:
    @pytest.fixture
    def store(self, tmp_path):
        return _LocalStore(root=str(tmp_path))

    def test_put_get(self, store):
        key = "satellite_products/sentinel2/sc1/B04.tif"
        data = b"\x00\x01\x02hello"
        assert store.put(key, data) == key
        assert store.get(key) == data

    def test_get_missing_raises(self, store):
        with pytest.raises(FileNotFoundError):
            store.get("satellite_products/ghost.tif")

    def test_exists(self, store):
        store.put("satellite_products/x.tif", b"data")
        assert store.exists("satellite_products/x.tif")
        assert not store.exists("satellite_products/missing.tif")

    def test_delete(self, store):
        key = "satellite_products/del.tif"
        store.put(key, b"gone")
        store.delete(key)
        assert not store.exists(key)

    def test_list(self, store):
        store.put("satellite_products/sentinel2/sc1/B04.tif", b"r")
        store.put("satellite_products/sentinel2/sc1/B08.tif", b"n")
        store.put("satellite_products/sentinel5p/sc2/v1.tif", b"p")
        keys = store.list()
        assert "satellite_products/sentinel2/sc1/B04.tif" in keys
        assert "satellite_products/sentinel2/sc1/B08.tif" in keys
        assert "satellite_products/sentinel5p/sc2/v1.tif" in keys
        assert len(keys) == 3

    def test_list_with_prefix(self, store):
        store.put("satellite_products/sentinel2/sc1/B04.tif", b"r")
        store.put("satellite_products/sentinel5p/sc2/v1.tif", b"p")
        keys = store.list(prefix="satellite_products/sentinel2/")
        assert len(keys) == 1
        assert keys[0].endswith("B04.tif")

    def test_checksum(self, store):
        key = "satellite_products/chk.tif"
        store.put(key, b"\x01\x02\x03")
        assert store.checksum(key) == "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"

    def test_presigned_url(self, tmp_path):
        store = _LocalStore(root=str(tmp_path))
        key = "satellite_products/url.tif"
        store.put(key, b"viewable")
        url = store.presigned_download_url(key)
        assert url is not None
        assert url.startswith("file://")
        assert "url.tif" in url

    def test_presigned_url_missing(self, store):
        assert store.presigned_download_url("satellite_products/ghost.tif") is None

    def test_nested_folders_created(self, store):
        key = "satellite_products/deeply/nested/folder/file.tif"
        store.put(key, b"nested")
        assert store.exists(key)

    def test_overwrite_allowed(self, store):
        key = "satellite_products/ov.tif"
        store.put(key, b"v1")
        store.put(key, b"v2")
        assert store.get(key) == b"v2"


class TestObjectStoreServiceDisabled:
    """ObjectStoreService.get() returns None when no backend is configured."""

    def test_disabled_raises_on_put(self):
        with pytest.raises(ObjectStoreDisabledError):
            ObjectStoreService.put(b"data")

    def test_disabled_raises_on_get(self):
        with pytest.raises(ObjectStoreDisabledError):
            ObjectStoreService.get("satellite_products/ghost.tif")

    def test_disabled_raises_on_exists(self):
        with pytest.raises(ObjectStoreDisabledError):
            ObjectStoreService.exists("satellite_products/ghost.tif")

    def test_disabled_raises_on_delete(self):
        with pytest.raises(ObjectStoreDisabledError):
            ObjectStoreService.delete("satellite_products/ghost.tif")

    def test_disabled_raises_on_list(self):
        with pytest.raises(ObjectStoreDisabledError):
            ObjectStoreService.list()

    def test_disabled_raises_on_checksum(self):
        with pytest.raises(ObjectStoreDisabledError):
            ObjectStoreService.checksum("satellite_products/ghost.tif")

    def test_disabled_presigned_returns_none_via_error(self):
        with pytest.raises(ObjectStoreDisabledError):
            ObjectStoreService.presigned_download_url("satellite_products/ghost.tif")



class TestObjectStoreServiceImmutability:
    """The public ObjectStoreService.put() should not duplicate identical content."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        ObjectStoreService._instance = None
        yield
        ObjectStoreService._instance = None

    def test_duplicate_content_returns_existing_key(self, tmp_path):
        import app.core.config as config
        orig = config.settings.OBJECT_STORE_ENDPOINT
        config.settings.OBJECT_STORE_ENDPOINT = ""
        try:
            backend = _LocalStore(root=str(tmp_path))
            ObjectStoreService._instance = backend
            key1 = ObjectStoreService.put(b"payload", source="s2", scene_id="sc1", ext="tif")
            key2 = ObjectStoreService.put(b"payload", source="s2", scene_id="sc1", ext="tif")
            assert key1 == key2
            assert tmp_path.joinpath("object_store", key1[len("satellite_products/"):]).is_file()
        finally:
            config.settings.OBJECT_STORE_ENDPOINT = orig

    def test_different_content_raises_on_existing_key(self, tmp_path):
        import app.core.config as config
        orig = config.settings.OBJECT_STORE_ENDPOINT
        config.settings.OBJECT_STORE_ENDPOINT = ""
        try:
            backend = _LocalStore(root=str(tmp_path))
            ObjectStoreService._instance = backend
            ObjectStoreService.put(b"first", source="s2", scene_id="sc1", ext="tif")
            with pytest.raises(ObjectStoreError):
                ObjectStoreService.put(b"second", source="s2", scene_id="sc1", ext="tif")
        finally:
            config.settings.OBJECT_STORE_ENDPOINT = orig

    def test_put_satellite_band(self, tmp_path):
        import app.core.config as config
        orig = config.settings.OBJECT_STORE_ENDPOINT
        config.settings.OBJECT_STORE_ENDPOINT = ""
        try:
            backend = _LocalStore(root=str(tmp_path))
            ObjectStoreService._instance = backend
            key = ObjectStoreService.put_satellite_band(
                b"band", source="sentinel2", scene_id="S2A_MSIL1C_20260801", band="B04",
            )
            assert key.endswith("/B04.tif")
            assert ObjectStoreService.get(key) == b"band"
        finally:
            config.settings.OBJECT_STORE_ENDPOINT = orig

    def test_put_satellite_product(self, tmp_path):
        import app.core.config as config
        orig = config.settings.OBJECT_STORE_ENDPOINT
        config.settings.OBJECT_STORE_ENDPOINT = ""
        try:
            backend = _LocalStore(root=str(tmp_path))
            ObjectStoreService._instance = backend
            key = ObjectStoreService.put_satellite_product(
                b"ndvi", source="sentinel2", scene_id="S2A_MSIL1C_20260801",
                product_name="ndvi", ext="tif",
            assert key.endswith("/ndvi.tif")
            assert ObjectStoreService.get(key) == b"ndvi"
        finally:
            config.settings.OBJECT_STORE_ENDPOINT = orig

class TestObjectStoreServiceE2E:
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        ObjectStoreService._instance = None
        yield
        ObjectStoreService._instance = None

    def test_full_roundtrip(self, tmp_path):
        import app.core.config as config
        orig = config.settings.OBJECT_STORE_ENDPOINT
        config.settings.OBJECT_STORE_ENDPOINT = ""
        try:
            backend = _LocalStore(root=str(tmp_path))
            ObjectStoreService._instance = backend

            # Simulate a satellite band upload.
            band_data = bytes(range(256))
            key = ObjectStoreService.put(
                band_data,
                source="sentinel2",
                scene_id="S2A_MSIL1C_20260801T045621_N0510_R094_T30TVK_20260801T064955",
                sub_key="B04",
                ext="tif",
            )
            assert key.startswith("satellite_products/sentinel2/")

            # Retrieve and verify integrity.
            got = ObjectStoreService.get(key)
            assert got == band_data
            assert ObjectStoreService.exists(key)
            assert ObjectStoreService.checksum(key) == hashlib.sha256(band_data).hexdigest()

            # Verify presigned URL.
            url = ObjectStoreService.presigned_download_url(key, expires_in=600)
            assert url is not None
            assert url.startswith("file://")

            # List scoped to the scene.
            listed = ObjectStoreService.list(
                prefix="satellite_products/sentinel2/S2A_MSIL1C_20260801T045621"
            )
            assert len(listed) == 1
            assert listed[0].endswith("B04.tif")

            # Cleanup.
            ObjectStoreService.delete(key)
            assert not ObjectStoreService.exists(key)
        finally:
            config.settings.OBJECT_STORE_ENDPOINT = orig

    def test_get_satellite_band(self, tmp_path):
        import app.core.config as config
        orig = config.settings.OBJECT_STORE_ENDPOINT
        config.settings.OBJECT_STORE_ENDPOINT = ""
        try:
            backend = _LocalStore(root=str(tmp_path))
            ObjectStoreService._instance = backend
            key = ObjectStoreService.put_satellite_band(
                b"band", source="sentinel2", scene_id="S2A_MSIL1C_20260801", band="B08",
            )
            assert ObjectStoreService.get_satellite_band(key) == b"band"
        finally:
            config.settings.OBJECT_STORE_ENDPOINT = orig
