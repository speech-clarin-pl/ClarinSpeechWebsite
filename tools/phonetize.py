#!/usr/bin/env python
# -*- coding: utf-8 -*-

import phonetisaurus

from config import config, db

model = phonetisaurus.Phonetisaurus(config.phonetisaurus_model)

pl_sampa_map = {'ni': "n'", 'si': "s'", 'tsi': "ts'", 'zi': "z'", 'dzi': "dz'", 'en': 'e~', 'on': 'o~'}
pl_ipa_map = {'e': u'ɛ', 'en': u'ɛ̃', 'I': u'ɨ', 'o': u'ɔ', 'on': u'ɔ̃', 'si': u'ɕ', 'dz': u'dz', 'dzi': u'dʑ',
              'dZ': u'dʐ', 'g': u'ɡ', 'ni': u'ɲ', 'S': u'ʂ', 'tsi': u'tɕ', 'ts': u'ts', 'tS': u'tʂ', 'zi': u'ʑ',
              'Z': u'ʐ'}

pl_script_map = {'sampa': pl_sampa_map, 'ipa': pl_ipa_map}


def phonetize_word(word, script):
    script_map = None
    if script and script in pl_script_map:
        script_map = pl_script_map[script]

    task = db.clarin.phonetizer.find_one({'text': word})
    if task:
        trans_arr = task['output']
    else:
        results = model.Phoneticize(word.encode('utf-8'), 100, 500, 10, False, False, 0.8)
        trans_arr = []
        for result in results:
            pronunciation = [model.FindOsym(u) for u in result.Uniques]
            trans_arr.append(u' '.join(pronunciation))

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
            ret.append(u' '.join(word))
        return ret
    else:
        return trans_arr
