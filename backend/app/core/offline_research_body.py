"""The same proven pre-parser 2 MiB bound, scoped only to offline evidence."""
import re
from app.core.annotation_body import AnnotationBodyLimit


class OfflineResearchBodyLimit(AnnotationBodyLimit):
    def __init__(self,app,*,prefix):
        super().__init__(app,prefix=prefix)
        self.pattern=re.compile(re.escape(prefix)+r'/cases/[^/]+/segmentations/[^/]+/research-evidence/verify/?$')
