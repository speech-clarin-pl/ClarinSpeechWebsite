import json
from pathlib import Path

from pymongo import MongoClient


class Config:
    def __init__(self):
        self.proj_root = Path(Path(__file__).parent).absolute()
        self.work_dir = self.proj_root / 'work'
        self.phonetisaurus_model = self.proj_root / 'model/phonetisaurus/model.fst'
        self.phonetisaurus_bin = Path('/home/guest/apps/kaldi/tools/phonetisaurus-g2p/phonetisaurus-g2pfst')
        self.emu = lambda: None
        self.emu.projects_per_page = 10
        self.emu.webapp_port = 17890
        self.emu.master_password = 'masterpassword'
        self.corpora_dir = Path('/dane/korpusy')
        self.allow_res_delete = True

    def load(self, config_path):
        try:
            with open(config_path) as f:
                config_file = json.load(f)
        except IOError:
            return

        if 'proj_root' in config_file:
            self.proj_root = Path(config_file['proj_root'])
        if 'work_dir' in config_file:
            self.work_dir = Path(config_file['work_dir'])
        if 'phonetisaurus_model' in config_file:
            self.phonetisaurus_model = Path(config_file['phonetisaurus_model'])
        if 'phonetisaurus_bin' in config_file:
            self.phonetisaurus_bin = Path(config_file['phonetisaurus_bin'])
        if 'emu' in config_file:
            if 'projects_per_page' in config_file['emu']:
                self.emu.projects_per_page = config_file['emu']['projects_per_page']
            if 'webapp_port' in config_file['emu']:
                self.emu.webapp_port = config_file['emu']['webapp_port']
            if 'master_password' in config_file['emu']:
                self.emu.master_password = config_file['emu']['master_password']
        if 'corpora_dir' in config_file:
            self.corpora_dir = Path(config_file['corpora_dir'])
        if 'allow_res_delete' in config_file:
            self.allow_res_delete = config_file['allow_res_delete']


config = Config()
config.load(config.proj_root / 'config.json')
db = MongoClient()
