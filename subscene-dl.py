import io
import re
import os
import sys
import time
import itertools
import unicodedata
import zipfile
from collections import defaultdict
import subscene_api as subscene
from guessit import guessit
from pprint import pprint


wanted_language = "English"
guessit_options = {
    'date_year_first': True,
    'episode_prefer_number': True
}


#: Subtitle extensions
SUBTITLE_EXTENSIONS = ('.srt', '.sub', '.smi', '.txt', '.ssa', '.ass', '.mpl')
#: Video extensions
VIDEO_EXTENSIONS = ('.3g2', '.3gp', '.3gp2', '.3gpp', '.60d', '.ajp', '.asf', '.asx', '.avchd', '.avi', '.bik',
                    '.bix', '.box', '.cam', '.dat', '.divx', '.dmf', '.dv', '.dvr-ms', '.evo', '.flc', '.fli',
                    '.flic', '.flv', '.flx', '.gvi', '.gvp', '.h264', '.m1v', '.m2p', '.m2ts', '.m2v', '.m4e',
                    '.m4v', '.mjp', '.mjpeg', '.mjpg', '.mkv', '.moov', '.mov', '.movhd', '.movie', '.movx', '.mp4',
                    '.mpe', '.mpeg', '.mpg', '.mpv', '.mpv2', '.mxf', '.nsv', '.nut', '.ogg', '.ogm' '.ogv', '.omf',
                    '.ps', '.qt', '.ram', '.rm', '.rmvb', '.swf', '.ts', '.vfw', '.vid', '.video', '.viv', '.vivo',
                    '.vob', '.vro', '.wm', '.wmv', '.wmx', '.wrap', '.wvx', '.wx', '.x264', '.xvid')



def is_meta_match(x, y):
    if x['type'] == 'movie' and y['type'] == 'movie':
        return True

    if x['type'] == 'episode' and y['type'] == 'episode':
        if x['season'] == y['season']:
            if 'episode' not in x or 'episode' not in y:
                return 'date' in x and 'date' in y and x['date'] == y['date']
            if isinstance(x['episode'], list):
                i=y['episode']
                return bool(set(x['episode']).intersection(i if isinstance(i, list) else [i]))
            if isinstance(y['episode'], list):
                return x['episode'] in y['episode']
            return x['episode'] == y['episode']
        return False


def cleanchar(text):
    text = unicodedata.normalize('NFKD', text)
    text = re.sub(u'[\u2013\u2014\u3161\u1173\uFFDA]', '-', text)
    text = re.sub(u'[\u00B7\u2000-\u206F\u22C5\u318D]', '.', text)
    return text


def search_subscene(title):
    film = subscene.search(title, "en", 0)
    for subtitle in film.subtitles:
        if subtitle.language == wanted_language:
            title = cleanchar(subtitle.title)
            subtitle_meta = guessit(title, guessit_options)
            subtitle_meta.setdefault('season', 1)
            subtitle_meta['filename'] = title
            subtitle_meta['subtitle_object'] = subtitle
            subtitle_meta['session_pack'] = subtitle_meta['type'] == 'episode' and (
                'episode' not in subtitle_meta or isinstance(subtitle_meta['episode'], list)
            )
            yield subtitle_meta


def download_single_sub(video_filename, ziplink):
    r = subscene.request_session.get(ziplink, headers=subscene.HEADERS)
    html = r.content
    with zipfile.ZipFile(io.BytesIO(html)) as z:
        # print("Found sub: "+ziplink)
        for infofile in z.infolist()[:1]:
            sub_ext = os.path.splitext(infofile.filename)[1]
            vid_name = os.path.splitext(video_filename)[0]
            if savepath:
                vid_name = os.path.join(savepath, os.path.split(vid_name)[1])
            file = open(vid_name + sub_ext, 'wb')
            file.write(z.read(infofile))
            print("File downloaded: ", vid_name + sub_ext)


def download_sesson_pack(v_metas, ziplink):
    r = subscene.request_session.get(ziplink, headers=subscene.HEADERS)
    html = r.content
    with zipfile.ZipFile(io.BytesIO(html)) as z:
        # print("Found season pack sub: "+ziplink)
        for infofile in z.infolist():
            zip_meta = guessit(cleanchar(infofile.filename), guessit_options)
            zip_meta.setdefault('season', 1)
            zip_meta['session_pack'] = False
            # print("Inside zip:"+infofile.filename)
            for v_meta in filter(lambda v: not v['downloaded'] and is_meta_match(v, zip_meta), v_metas):
                sub_ext = os.path.splitext(infofile.filename)[1]
                vid_name = os.path.splitext(v_meta['filename'])[0]
                if savepath:
                    vid_name = os.path.join(savepath, os.path.split(vid_name)[1])
                file = open(vid_name + sub_ext, 'wb')
                file.write(z.read(infofile))
                print("File downloaded: ", vid_name + sub_ext)
                v_meta['downloaded'] = True


def download_subtitles(files):
    video_metas = defaultdict(list)
    for f in files:
        video_meta = guessit(cleanchar(f), guessit_options)
        video_meta['filename'] = f
        video_meta['downloaded'] = False
        video_meta.setdefault('season', 1)
        title = unicodedata.normalize('NFKD', video_meta['title'])
        video_metas[title].append(video_meta)

    for title, v_metas in video_metas.items():
        subtitle_metas = list(search_subscene(title))

        #season packs have priority
        for subtitle_meta in filter(lambda s: s['session_pack'], subtitle_metas):
            # print(subtitle_meta)
            #if pack does not have the ep we want, skip it
            if 'episode' in subtitle_meta and isinstance(subtitle_meta['episode'], list):
                eps = [v['episode'] for v in v_metas if not v['downloaded']]
                eps = set(itertools.chain.from_iterable([i if isinstance(i, list) else [i] for i in eps]))
                if not eps.intersection(subtitle_meta['episode']):
                    continue
            # print("trying to download:"+subtitle_meta['filename'])
            download_sesson_pack(v_metas, subtitle_meta['subtitle_object'].zipped_url)
            #if all subs downloaded
            if all([v['downloaded'] for v in v_metas]):
                break

        #download others files that season pack doesnt get
        for video_meta in filter(lambda v: not v['downloaded'], v_metas):
            for subtitle_meta in filter(lambda s: is_meta_match(video_meta, s), subtitle_metas):
                download_single_sub(video_meta['filename'], subtitle_meta['subtitle_object'].zipped_url)
                break

        time.sleep(3)


def find_video_files(path):
    if os.path.isdir(path):
        allfiles=[]
        for root, dirs, files in os.walk(path):
            allfiles.extend([os.path.join(root,f) for f in files])
        videos = list(filter(lambda f: f.endswith(VIDEO_EXTENSIONS), allfiles))
        for v in videos:
            if not any(p.startswith(os.path.splitext(v)[0]) and p.endswith(SUBTITLE_EXTENSIONS) for p in allfiles):
                yield v

    elif path.endswith(VIDEO_EXTENSIONS):
        dirpath, filename = os.path.split(path)
        dirpath = dirpath or '.'
        fileroot, fileext = os.path.splitext(filename)

        for p in os.listdir(dirpath):
            if p.startswith(fileroot) and p.endswith(SUBTITLE_EXTENSIONS):
                return
        yield path


'''
subscene-dl.py filename.mkv [where_to_save]
    will download sub for filename.mkv

subscene-dl.py /somedir
    will download subs for all video files in /somedir
    
note: subscene-dl.py will skip any file that already have subs
'''
if __name__ == "__main__":
    if len(sys.argv) > 2:
        savepath = sys.argv[2]
    videos = find_video_files(os.path.normpath(sys.argv[1]))
    download_subtitles(videos)
