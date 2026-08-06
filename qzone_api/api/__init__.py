from .api_base import ApiBase
from .api_zone import ApiZone
from .api_feed import ApiFeed
from .api_album import ApiAlbum

class QzoneApi(ApiZone, ApiFeed, ApiAlbum):
    pass

__all__ = ['QzoneApi']
