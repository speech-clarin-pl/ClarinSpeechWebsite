import argparse
import codecs
import re

from pymongo import MongoClient
from tqdm import tqdm

db = MongoClient()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='phonetic_dictionary',
                                     description='Loads the phonetic dictionary into the database')
    parser.add_argument('dict', help='The phonetic dictioanry')

    args = parser.parse_args()

    print 'Loading file...'
    sp = re.compile('\s+')
    dict = {}
    with codecs.open(args.dict, encoding='utf-8') as f:
        for l in f:
            p = sp.split(l.strip())
            if len(p) < 2:
                continue
            word = p[0]
            trans = ' '.join(p[1:])
            if word not in dict:
                dict[word] = []
            dict[word].append(trans)

    print 'Cleaning the old database...'
    db.clarin.phonetizer.remove({})

    count = len(dict)
    print 'Updating the database...'
    for word, trans in tqdm(dict.iteritems(), total=count):
        db.clarin.phonetizer.insert_one({'text': word, 'output': trans})

    print 'Done!'
