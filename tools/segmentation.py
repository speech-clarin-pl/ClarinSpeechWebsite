import codecs
import json
import re
from collections import OrderedDict
from os import close
from pathlib import Path
from tempfile import mkstemp

import tgt

from config import config
from tools.phonetize import pl_sampa_map, pl_ipa_map
from tools.utils import wav_extract, insert_file

EPSILON = 0.01
besi = re.compile('^.*_[BESI]$')


class Segment:
    def __init__(self, start, len, text, idgen):
        assert start >= 0 and len >= 0, 'start or len smaller than 0 for ' + text

        self.start = round(start, 2)
        self.len = round(len, 2)
        self.end = round(self.start + self.len, 2)
        self.text = text
        self.id = next(idgen)

    def wraps(self, other):
        return other.start - self.start > -EPSILON and other.end - self.end < EPSILON


class Level:
    def __init__(self, idgen):
        self.segments = []
        self.idgen = idgen

    def add(self, start, len, text):
        self.segments.append(Segment(start, len, text, self.idgen))

    def sort(self):
        self.segments = sorted(self.segments, key=lambda seg: seg.start)

    def fill_gaps(self):
        self.sort()
        gaps = []
        for prev, next in zip(self.segments, self.segments[1:]):
            if next.start > prev.end:
                gaps.append(Segment(prev.end, next.start - prev.end, '', self.idgen))
            if next.start < prev.end:
                prev.end = next.start
                prev.len = prev.end - prev.start
        self.segments.extend(gaps)
        self.sort()

    def contains(self, segment):
        self.sort()
        start = self.segments[0].start
        end = self.segments[-1].end
        return segment.start - start > -EPSILON and segment.end - end < EPSILON

    def get_annotation(self, name, labelname, samplerate=16000.0, get_segments=True, ph_labels=None):

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

    def get_links(self, other_ctm):
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

    def __next__(self):
        self.id_cnt += 1
        return self.id_cnt


class Segmentation:
    def __init__(self):
        self.idgen = IDgen()
        self.words = Level(self.idgen)
        self.phonemes = Level(self.idgen)

    def get_limits(self):
        self.phonemes.sort()
        return (self.phonemes.segments[0].start, self.phonemes.segments[-1].end)

    def read(self, file, rm_besi=True, script=None):
        with codecs.open(file, encoding='utf-8', mode='r') as f:
            for l in f:
                tok = l.strip().split(' ')
                assert len(tok) == 5, f'Wrong tok count in file {file}: {l}'
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

        self.words.fill_gaps()
        self.phonemes.fill_gaps()

    def write(self, file):
        with codecs.open(file, encoding='utf-8', mode='w') as f:
            for seg in self.phonemes.segments:
                seg.word = False
            for seg in self.words.segments:
                seg.word = True
            a = self.phonemes.segments
            a.extend(self.words.segments)
            a = sorted(a, key=lambda seg: seg.start)
            for seg in a:
                if not seg.word:
                    f.write('@')
                f.write(f'input 1 {seg.start} {seg.len} {seg.text}\n')

    def write_trans(self, file):
        with codecs.open(file, encoding='utf-8', mode='w') as f:
            for seg in self.words.segments:
                f.write(seg.text + ' ')
            f.write('\n')

    def subtract_start(self):
        seg_start = self.phonemes.segments[0].start
        for seg in self.phonemes.segments:
            seg.start -= seg_start
            seg.end -= seg_start
        for seg in self.words.segments:
            seg.start -= seg_start
            seg.end -= seg_start

    def get_textgrid(self):
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

    def get_utt_level(self, name):
        level = Level(self.idgen)
        min = max = 0
        for seg in self.words.segments:
            if min > seg.start:
                min = seg.start
            if max < seg.end:
                max = seg.end
        level.add(min, max, name)
        return level

    def split_by_silence(self, sil_len=0.5):
        seg = Segmentation()
        ret = [seg]
        pl = len(self.phonemes.segments)
        for id, ph in enumerate(self.phonemes.segments):
            if ph.text == 'sil' and ph.len >= sil_len and id > 0 and id < (pl - 1):
                seg.phonemes.add(ph.start, ph.len / 2, ph.text)
                seg = Segmentation()
                ret.append(seg)
                seg.phonemes.add(ph.start + ph.len / 2, ph.len / 2, ph.text)
            else:
                seg.phonemes.add(ph.start, ph.len, ph.text)

        for seg in ret:
            for w in self.words.segments:
                if seg.phonemes.contains(w):
                    seg.words.segments.append(w)

        return ret


def segmentation_to_textgrid(file, rm_besi=True, script=None):
    seg = Segmentation()
    seg.read(file, rm_besi=rm_besi, script=script)
    return seg.get_textgrid()


def segmentation_to_emu_annot(file, name, samplerate=16000.0, rm_besi=True, script=None):
    seg = Segmentation()
    seg.read(file, rm_besi=rm_besi, script=script)

    annot = OrderedDict()

    annot['name'] = name
    annot['annotates'] = name + '.wav'
    annot['sampleRate'] = samplerate

    levels = []
    annot['levels'] = levels

    utterance = seg.get_utt_level(name)
    words = seg.words
    phonemes = seg.phonemes

    levels.append(utterance.get_annotation('Utterance', 'Utterance', get_segments=False))

    levels.append(words.get_annotation('Word', 'Word', samplerate))

    levels.append(phonemes.get_annotation('Phoneme', 'Phoneme', samplerate,
                                          ph_labels=[('SAMPA', pl_sampa_map), ('IPA', pl_ipa_map)]))

    uttlinks = utterance.get_links(words)
    wordlinks = words.get_links(phonemes)

    annot['links'] = uttlinks + wordlinks

    return json.dumps(annot, indent=4)


def split_segmentation(wav_file, seg_file, rm_besi=True, script=None, sil_len=0.5):
    seg = Segmentation()
    seg.read(seg_file, rm_besi=rm_besi, script=script)
    splits = seg.split_by_silence(sil_len)

    ret = []
    for split in splits:
        fd, tmp = mkstemp(dir=config.work_dir)
        close(fd)
        tmp_wav = Path(config.work_dir) / tmp

        lim = split.get_limits()
        wav_extract(wav_file, tmp_wav, lim[0], lim[1])

        fd, tmp = mkstemp(dir=config.work_dir)
        close(fd)
        tmp_trans = Path(config.work_dir) / tmp

        split.write_trans(tmp_trans)

        fd, tmp = mkstemp(dir=config.work_dir)
        close(fd)
        tmp_seg = Path(config.work_dir) / tmp

        split.subtract_start()
        split.write(tmp_seg)

        wav_id = insert_file(tmp_wav, 'audio')
        trans_id = insert_file(tmp_trans, 'transcript')
        seg_id = insert_file(tmp_seg, 'segmentation')

        ret.append((wav_id, trans_id, seg_id))

    return ret
