#!/usr/bin/env python
# -*- coding: utf-8 -*-
from subprocess import run, PIPE, DEVNULL

from config import config, db

pl_sampa_map = {'ni': "n'", 'si': "s'", 'tsi': "ts'", 'zi': "z'", 'dzi': "dz'", 'en': 'e~', 'on': 'o~'}
pl_ipa_map = {'e': 'ɛ', 'en': 'ɛ̃', 'I': 'ɨ', 'o': 'ɔ', 'on': 'ɔ̃', 'si': 'ɕ', 'dz': 'dz', 'dzi': 'dʑ',
              'dZ': 'dʐ', 'g': 'ɡ', 'ni': 'ɲ', 'S': 'ʂ', 'tsi': 'tɕ', 'ts': 'ts', 'tS': 'tʂ', 'zi': 'ʑ',
              'Z': 'ʐ'}

pl_script_map = {'sampa': pl_sampa_map, 'ipa': pl_ipa_map}


def phonetize_word(word, script, use_cache=True):
    script_map = None
    if script and script in pl_script_map:
        script_map = pl_script_map[script]

    task = None
    if use_cache:
        task = db.clarin.phonetizer.find_one({'text': word})

    if task:
        trans_arr = task['output']
    else:
        trans_arr = []
        proc = run(
            [f'{config.phonetisaurus_bin.absolute()}', f'--model={config.phonetisaurus_model.absolute()}',
             '--nbest=100', '--beam=500', '--thresh=10', '--pmass=0.8', f'--word={word}'], stdout=PIPE, stderr=DEVNULL)
        out = proc.stdout.decode('utf-8').strip().split('\n')
        for t in out:
            t = t.split('\t')[2]
            trans_arr.append(t)

        if use_cache:
            db.clarin.phonetizer.insert_one({'text': word, 'output': trans_arr})

    if script_map:
        ret = []
        for trans in trans_arr:
            word = []
            for ph in trans.split(' '):
                if ph in script_map:
                    word.append(script_map[ph])
                else:
                    word.append(ph)
            ret.append(' '.join(word))
        return ret
    else:
        return trans_arr


# unit test
if __name__ == '__main__':
    print(phonetize_word('przykład', 'ipa', use_cache=False))
