import json
import os

from pymongo import MongoClient


class Config:
    def __init__(self):
        self.proj_root = os.path.dirname(os.path.realpath(__file__))
        self.work_dir = os.path.realpath(os.path.join(self.proj_root, 'work'))
        self.phonetisaurus_model = os.path.join(self.proj_root, 'model/phonetisaurus/model.fst')
        self.emu = lambda: None
        self.emu.projects_per_page = 10
        self.emu.webapp_port = 17890
        self.emu.master_password = 'masterpassword'
        self.corpora_dir = '/dane/korpusy'

    def load(self, config_path):
        try:
            with open(config_path) as f:
                config_file = json.load(f)
        except:
            return

        if 'proj_root' in config_file:
            self.proj_root = config_file['proj_root']
        if 'work_dir' in config_file:
            self.work_dir = config_file['work_dir']
        if 'phonetisaurus_model' in config_file:
            self.phonetisaurus_model = config_file['phonetisaurus_model']
        if 'emu' in config_file:
            if 'proj_root' in config_file['emu']:
                self.emu.projects_per_page = config_file['emu']['projects_per_page']
            if 'webapp_port' in config_file['emu']:
                self.emu.webapp_port = config_file['emu']['webapp_port']
            if 'master_password' in config_file['emu']:
                self.emu.master_password = config_file['emu']['master_password']
        if 'corpora_dir' in config_file:
            self.corpora_dir = config_file['corpora_dir']


config = Config()
config.load(os.path.join(config.proj_root, 'config.json'))
db = MongoClient()
