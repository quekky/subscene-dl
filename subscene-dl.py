import io
import re
import os
import sys
import time
import unicodedata
import zipfile
from collections import defaultdict
import subscene_api as subscene
from guessit import guessit

aliases = {
    'running man': 'Running Man 런닝맨'
}

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
    return x['type'] == 'episode' and y['type'] == 'episode' and not y['session_pack'] and \
           ((x['season'] == y['season'] and x['episode'] == y['episode']) or
            ('date' in x and 'date' in y and x['date'] == y['date']))


def search_subscene(title):
    film = subscene.search(title, "en", 0)
    for subtitle in film.subtitles:
        if subtitle.language == wanted_language:
            title = re.sub(u'[\u2013\u2014\u3161]', '-', subtitle.title)
            subtitle_meta = guessit(title, guessit_options)
            subtitle_meta.setdefault('season', 1)
            subtitle_meta['subtitle_object'] = subtitle
            subtitle_meta['session_pack'] = subtitle_meta['type'] == 'episode' and (
                'episode' not in subtitle_meta or isinstance(subtitle_meta['episode'], list) and len(subtitle_meta['episode']) >= 4
            )
            yield subtitle_meta


def download_single_sub(video_filename, ziplink):
    r = subscene.request_session.get(ziplink, headers=subscene.HEADERS)
    html = r.content
    with zipfile.ZipFile(io.BytesIO(html)) as z:
        for infofile in z.infolist()[:1]:
            sub_ext = os.path.splitext(infofile.filename)[1]
            vid_name = os.path.splitext(video_filename)[0]
            file = open(vid_name + sub_ext, 'wb')
            file.write(z.read(infofile))
            print("File downloaded: ", vid_name + sub_ext)


def download_sesson_pack(v_metas, ziplink):
    r = subscene.request_session.get(ziplink, headers=subscene.HEADERS)
    html = r.content
    with zipfile.ZipFile(io.BytesIO(html)) as z:
        for infofile in z.infolist():
            zip_meta = guessit(infofile.filename, guessit_options)
            zip_meta.setdefault('season', 1)
            zip_meta['session_pack'] = False
            for v_meta in filter(lambda v: is_meta_match(v, zip_meta), v_metas):
                sub_ext = os.path.splitext(infofile.filename)[1]
                vid_name = os.path.splitext(v_meta['filename'])[0]
                file = open(vid_name + sub_ext, 'wb')
                file.write(z.read(infofile))
                print("File downloaded: ", vid_name + sub_ext)
                v_meta['downloaded'] = True


def download_subtitles(files):
    video_metas = defaultdict(list)
    for f in files:
        video_meta = guessit(f, guessit_options)
        video_meta['filename'] = f
        video_meta['downloaded'] = False
        video_meta.setdefault('season', 1)
        title = unicodedata.normalize('NFKD', video_meta['title'])
        video_metas[title].append(video_meta)

    for title, v_metas in video_metas.items():
        session_pack = len(v_metas) >= 4
        if title.lower() in aliases:
            title = aliases[title.lower()]

        subtitle_metas = search_subscene(title)

        if session_pack:
            for subtitle_meta in filter(lambda s: s['session_pack'], subtitle_metas):
                download_sesson_pack(v_metas, subtitle_meta['subtitle_object'].zipped_url)
                #if all subs downloaded
                if any([v['downloaded'] for v in v_metas]):
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
subscene-dl.py filename.mkv
    will download sub for filename.mkv

subscene-dl.py /somedir
    will download subs for all video files in /somedir
    
note: subscene-dl.py will skip any file that already have subs
'''
if __name__ == "__main__":
    videos = find_video_files(os.path.normpath(sys.argv[1]))
    download_subtitles(videos)
