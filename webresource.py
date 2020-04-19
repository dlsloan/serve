from pathlib import Path
from webcfg import WebCFG

class WebResource:
    def __init__(self, web_path:Path, local_path:Path, webcfg:WebCFG):
        self.web_path = web_path
        self.local_path = local_path
        self.webcfg = webcfg
        self.mime = self.webcfg.get_mime_type(web_path, local_path)


    