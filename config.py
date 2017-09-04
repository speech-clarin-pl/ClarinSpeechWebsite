import os

from pymongo import MongoClient


# TODO -- argparse
class Config:
    def __init__(self):
        self.proj_root = os.path.dirname(os.path.realpath(__file__))
        self.work_dir = os.path.join(self.proj_root, 'work')
        self.phonetisaurus_model = os.path.join(self.proj_root, 'model/phonetisaurus/model.fst')
        self.emu = lambda: None
        self.emu.projects_per_page = 10
        self.emu.webapp_port = 17890


config = Config()
db = MongoClient()