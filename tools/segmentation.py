import codecs
import json
import re
from collections import OrderedDict
from tools.phonetize import pl_sampa_map, pl_ipa_map

import tgt

EPSILON = 0.01
besi = re.compile('^.*_[BESI]$')


class Segment:
    def __init__(self, start, len, text, idgen):
        assert start >= 0 and len >= 0, 'start or len smaller than 0 for ' + text

        self.start = start
        self.len = len
        self.end = round(self.start + self.len, 2)
        self.text = text
        self.id = idgen.next()

    def wraps(self, other):
        return other.start - self.start > -EPSILON and other.end - self.end < EPSILON


class Level:
    def __init__(self, idgen):
        self.segments = []
        self.idgen = idgen

    def add(self, start, len, text):
        self.segments.append(Segment(start, len, text, self.idgen))

    def getAnnotation(self, name, labelname, samplerate=16000, get_segments=True, ph_labels=None):

        level = OrderedDict()

        level['name'] = name
        if get_segments:
            level['type'] = 'SEGMENT'
        else:
            level['type'] = 'ITEM'

        items = []
        level['items'] = items

        for seg in self.segments:
            item = OrderedDict()
            items.append(item)

            item['id'] = seg.id

            if get_segments:
                item['sampleStart'] = int(samplerate * seg.start)
                item['sampleDur'] = int(samplerate * seg.len)

            labels = []
            item['labels'] = labels

            label = OrderedDict()
            labels.append(label)

            label['name'] = labelname

            label['value'] = seg.text

            if ph_labels:
                for scriptame, map in ph_labels:
                    label = OrderedDict()
                    labels.append(label)
                    label['name'] = scriptame
                    if seg.text in map:
                        label['value'] = map[seg.text]
                    else:
                        label['value'] = seg.text

        return level

    def getLinks(self, other_ctm):
        links = []

        for seg in self.segments:
            for other_seg in other_ctm.segments:
                if seg.wraps(other_seg):
                    link = OrderedDict()
                    links.append(link)
                    link['fromID'] = seg.id
                    link['toID'] = other_seg.id

        return links


class IDgen:
    def __init__(self):
        self.id_cnt = 0

    def next(self):
        self.id_cnt += 1
        return self.id_cnt


class Segmentation:
    def __init__(self):
        self.idgen = IDgen()
        self.words = Level(self.idgen)
        self.phonemes = Level(self.idgen)

    def read(self, file, rm_besi=True, script=None):
        with codecs.open(file, encoding='utf-8', mode='r') as f:
            for l in f:
                tok = l.strip().split(' ')
                assert len(tok) == 5, 'Wrong tok count in file {}: {}'.format(file, l)
                if tok[0][0] == '@':
                    ph = tok[4]

                    if rm_besi:
                        if besi.match(ph):
                            ph = ph[:-2]
                    if script == 'sampa':
                        if ph in pl_sampa_map:
                            ph = pl_sampa_map[ph]
                    elif script == 'ipa':
                        if ph in pl_ipa_map:
                            ph = pl_ipa_map[ph]

                    self.phonemes.add(round(float(tok[2]), 2), round(float(tok[3]), 2), ph)
                else:
                    self.words.add(round(float(tok[2]), 2), round(float(tok[3]), 2), tok[4])

    def getTextGrid(self):
        tg = tgt.TextGrid()
        t = tgt.IntervalTier(name='Word')
        for w in self.words.segments:
            t.add_interval(tgt.Interval(w.start, w.end, w.text))
        tg.add_tier(t)
        t = tgt.IntervalTier(name='Phoneme')
        for ph in self.phonemes.segments:
            t.add_interval(tgt.Interval(ph.start, ph.end, ph.text))
        tg.add_tier(t)

        return tgt.io.export_to_long_textgrid(tg)

    def getUttLevel(self, name):
        level = Level(self.idgen)
        min = max = 0
        for seg in self.words.segments:
            if min > seg.start:
                min = seg.start
            if max < seg.end:
                max = seg.end
        level.add(min, max, name)
        return level


def segmentation_to_textgrid(file, rm_besi=True, script=None):
    seg = Segmentation()
    seg.read(file, rm_besi=rm_besi, script=script)
    return seg.getTextGrid()


def segmentation_to_emu_annot(file, name, samplerate=16000.0, rm_besi=True, script=None):
    seg = Segmentation()
    seg.read(file, rm_besi=rm_besi, script=script)

    annot = OrderedDict()

    annot['name'] = name
    annot['annotates'] = name + '.wav'
    annot['sampleRate'] = samplerate

    levels = []
    annot['levels'] = levels

    utterance = seg.getUttLevel(name)
    words = seg.words
    phonemes = seg.phonemes

    levels.append(utterance.getAnnotation('Utterance', 'Utterance', get_segments=False))

    levels.append(words.getAnnotation('Word', 'Word', samplerate))

    levels.append(phonemes.getAnnotation('Phoneme', 'Phoneme', samplerate,
                                         ph_labels=[('SAMPA', pl_sampa_map), ('IPA', pl_ipa_map)]))

    uttlinks = utterance.getLinks(words)
    wordlinks = words.getLinks(phonemes)

    annot['links'] = uttlinks + wordlinks

    return json.dumps(annot, indent=4)
