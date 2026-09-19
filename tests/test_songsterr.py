import json
import zipfile
from pathlib import Path

from feedback_converter import songsterr as creator
from feedback_converter import songsterr_cli as creator_cli
from feedback_converter.songsterr import songsterr_to_tracks, write_feedpak


def test_main_video_keeps_full_mix_alternatives_and_excludes_stems(monkeypatch):
    rows = [{'videoId': 'stem', 'status': 'done', 'feature': 'backing'},
            {'videoId': 'alternate', 'status': 'done', 'feature': 'alternative', 'points': [1, 3]},
            {'videoId': 'primary', 'status': 'done', 'feature': None, 'points': [2, 4]},
            {'videoId': 'solo', 'status': 'done', 'feature': 'solo'},
            {'videoId': 'pending', 'status': 'pending', 'feature': 'alternative'}]
    monkeypatch.setattr(creator, '_get_bytes', lambda url: json.dumps(rows).encode())
    result = creator._main_video({'songId': 1, 'revisionId': 2})
    assert result['videoId'] == 'primary'
    assert [video['videoId'] for video in result['alternatives']] == ['alternate']
    assert result['alternatives'][0]['points'] == [1, 3]
    rows[:] = rows[:1]
    assert creator._main_video({'songId': 1, 'revisionId': 2}) is None


def test_unsuffixed_links_select_their_own_parts(monkeypatch):
    guitar = "https://www.songsterr.com/a/wsa/deftones-root-tab-s29211"
    bass = "https://www.songsterr.com/a/wsa/deftones-root-bass-tab-s29211"
    tracks = [{"partId": 0, "title": "Guitar"}, {"partId": 1, "title": "Bass"}]
    states = {
        guitar: {"meta": {"current": {"songId": 29211, "partId": 0, "tracks": tracks}}},
        bass: {"meta": {"current": {"songId": 29211, "partId": 1, "tracks": tracks}}},
    }
    monkeypatch.setattr(creator, "_page_state", states.__getitem__)
    monkeypatch.setattr(creator, "_download_part", lambda _meta, part_id: {"partId": part_id})

    song = creator.load_songsterr([guitar, bass])

    assert [(part["partId"], part["title"]) for part in song["parts"]] == [
        (0, "Guitar"), (1, "Bass")]


def test_inspection_discovers_tracks_video_and_safe_name(monkeypatch):
    url = "https://www.songsterr.com/a/wsa/band-song-tab-s123"
    meta = {
        "songId": 123, "revisionId": 456, "partId": 1,
        "title": 'Song: One?', "artist": "Band", "tracks": [
            {"partId": 0, "title": "Vocals"},
            {"partId": 1, "title": "Guitar", "isGuitar": True},
            {"partId": 2, "title": "Drums", "isDrums": True},
        ],
    }
    monkeypatch.setattr(creator, "_page_state", lambda _url: {"meta": {"current": meta}})
    monkeypatch.setattr(creator, "_get_bytes", lambda _url: json.dumps([
        {"status": "done", "feature": "alternative", "videoId": "alt", "points": [1]},
        {"status": "done", "feature": None, "videoId": "main", "points": [2, 3]},
    ]).encode())
    monkeypatch.setattr(creator, "_youtube_metadata", lambda _url: {
        "album": "Album", "year": 2001, "duration": 123})
    monkeypatch.setattr(creator, "_release_artwork", lambda *_args: {
        "album": "Album", "year": 2001, "cover_url": "https://example/cover.jpg",
        "cover_source": "Cover Art Archive"})

    result = creator.inspect_songsterr(url)

    assert result["video_url"] == "https://youtu.be/main"
    assert result["video_points"] == [2, 3]
    assert [track["supported"] for track in result["tracks"]] == [False, True, True]
    assert [track["role"] for track in result["tracks"]] == ["", "lead", "drums"]
    assert (result["album"], result["year"], result["cover_url"]) == (
        "Album", 2001, "https://example/cover.jpg")
    assert creator.feedpak_filename("Band", 'Song: One?', "Album") == "Band - Song_ One_ - Album.feedpak"


def test_release_metadata_prefers_original_studio_album(monkeypatch):
    response = {"recordings": [{"title": "The Art of Dying", "score": 100, "releases": [
        {"id": "live", "title": "The Flesh Alive", "status": "Official", "date": "2006-01-01",
         "release-group": {"id": "live-group", "title": "The Flesh Alive",
                           "primary-type": "Album", "secondary-types": ["Live"]}},
        {"id": "original", "title": "The Way of All Flesh", "status": "Official", "date": "2008-10-13",
         "release-group": {"id": "studio-group", "title": "The Way of All Flesh",
                           "primary-type": "Album", "secondary-types": []}},
        {"id": "reissue", "title": "The Way of All Flesh", "status": "Official", "date": "2022-09-09",
         "release-group": {"id": "studio-group", "title": "The Way of All Flesh",
                           "primary-type": "Album", "secondary-types": []}},
    ]}]}

    def get_bytes(url):
        if "musicbrainz.org" in url:
            return json.dumps(response).encode()
        if url.endswith("/release/original/"):
            raise OSError("No art on this edition")
        return json.dumps({"images": [{"front": True, "thumbnails": {
            "500": "http://example.test/cover.jpg"}}]}).encode()

    monkeypatch.setattr(creator, "_get_bytes", get_bytes)
    result = creator._release_artwork("Gojira", "The Art of Dying", "Wrong Video Album", 2012)

    assert result["album"] == "The Way of All Flesh"
    assert result["year"] == 2008
    assert result["cover_url"] == "https://example.test/cover.jpg"
    assert result["release_id"] == "reissue"


def test_inspection_never_uses_youtube_release_metadata(monkeypatch):
    url = "https://www.songsterr.com/a/wsa/band-song-tab-s123"
    meta = {"songId": 123, "revisionId": 456, "partId": 0,
            "title": "Song", "artist": "Band", "tracks": []}
    monkeypatch.setattr(creator, "_page_state", lambda _url: {"meta": {"current": meta}})
    monkeypatch.setattr(creator, "_main_video", lambda _meta: {
        "videoId": "main", "points": []})
    monkeypatch.setattr(creator, "_youtube_metadata", lambda _url: {
        "album": "Uploader Playlist", "year": 2026, "duration": 123})
    monkeypatch.setattr(creator, "_release_artwork", lambda *_args: {})

    result = creator.inspect_songsterr(url)

    assert result["album"] == ""
    assert result["year"] is None
    assert result["duration"] == 123


def test_creator_applies_editable_arrangement_names(monkeypatch, tmp_path):
    inspection = {"video_url": "audio", "meta": {"title": "Song", "artist": "Band"}}
    arrangement = {"name": "Source Guitar", "role": "lead"}
    captured = {}
    monkeypatch.setattr(creator_cli, "inspect_songsterr", lambda *_args, **_kwargs: inspection)
    monkeypatch.setattr(creator_cli, "load_songsterr_selection", lambda *_args: {})
    monkeypatch.setattr(creator_cli, "songsterr_to_tracks", lambda _song: ([arrangement], {}))
    monkeypatch.setattr(creator_cli, "prepare_audio", lambda *_args: tmp_path / "audio.opus")
    monkeypatch.setattr(creator_cli, "prepare_cover", lambda *_args: None)

    def write(arrangements, _timeline, _audio, output, **_kwargs):
        captured["arrangements"] = arrangements
        return output

    monkeypatch.setattr(creator_cli, "write_feedpak", write)
    creator_cli.create({
        "url": "https://www.songsterr.com/a/wsa/band-song-tab-s123",
        "selected_parts": [7], "roles": {"7": "rhythm"},
        "names": {"7": "Rhythm Guitar - Drop C"},
        "output_path": str(tmp_path / "song.feedpak"),
    })

    assert captured["arrangements"][0]["name"] == "Rhythm Guitar - Drop C"
    assert captured["arrangements"][0]["role"] == "rhythm"


def test_batch_continues_after_one_song_fails(monkeypatch):
    def fake_create(payload):
        if payload["title"] == "Broken":
            raise RuntimeError("audio unavailable")
        return {"output_path": f'{payload["title"]}.feedpak', "arrangements": 1, "lyrics": 0}

    monkeypatch.setattr(creator_cli, "create", fake_create)

    result = creator_cli.create_batch([{"title": "Good"}, {"title": "Broken"}])

    assert result["created"] == 1
    assert result["failed"] == 1
    assert result["results"][0]["ok"] is True
    assert result["results"][1] == {
        "ok": False, "title": "Broken", "error": "audio unavailable"}


def test_lrclib_lyrics_are_fetched_and_timed(monkeypatch):
    response = {
        "id": 42, "trackName": "Root", "artistName": "Deftones",
        "albumName": "Adrenaline", "duration": 221,
        "syncedLyrics": "[00:01.00]First line\n[00:03.50]Second line",
        "plainLyrics": "First line\nSecond line",
    }
    monkeypatch.setattr(creator, "_get_bytes", lambda url: json.dumps(response).encode())

    result = creator.fetch_synced_lyrics("Deftones", "Root", "Adrenaline", 221)

    assert result["provider"] == "LRCLIB"
    assert [line["w"] for line in result["events"]] == ["First line+", "Second line+"]
    assert [word["w"] for word in result["events"][0]["words"]] == ["First", "line+"]
    assert result["events"][0]["words"][0]["t"] == 1.0


def test_lyrics_fall_back_to_tolerant_search(monkeypatch):
    match = {
        "id": 7, "trackName": "Root", "artistName": "Deftones",
        "albumName": "Adrenaline", "duration": 221,
        "syncedLyrics": "[00:01.00]One\n[00:03.00]Two",
    }

    def response(url):
        if "/api/get?" in url:
            raise OSError("no exact match")
        return json.dumps([match]).encode()

    monkeypatch.setattr(creator, "_get_bytes", response)
    monkeypatch.setattr(creator.time, "sleep", lambda _seconds: None)

    result = creator.fetch_synced_lyrics(
        "Deftones", "Root (Official Video)", "Adrenaline", 222)

    assert result["match_method"] == "search"
    assert result["matched_title"] == "Root"


def test_lyrics_fall_back_to_netease_catalog(monkeypatch):
    def response(url):
        if "lrclib.net" in url:
            raise OSError("not in LRCLIB")
        if "/netease/search?" in url:
            return json.dumps({"result": {"songs": [{
                "id": 17, "name": "Root", "duration": 220826,
                "artists": [{"name": "Deftones"}], "album": {"name": "Adrenaline"},
            }]}}).encode()
        return json.dumps({"metadata": {"rawData": {"lrc": {
            "lyric": "[00:42.65]First line\n[00:52.53]Second line"
        }}}}).encode()

    monkeypatch.setattr(creator, "_get_bytes", response)
    monkeypatch.setattr(creator.time, "sleep", lambda _seconds: None)

    result = creator.fetch_synced_lyrics("Deftones", "Root", "Adrenaline", 221)

    assert result["provider"] == "NetEase via Lyrically"
    assert result["events"][0]["t"] == 42.65


def test_video_sync_expands_repeat_playback():
    part = {
        "instrument": "Electric Guitar", "strings": 6,
        "tuning": [64, 59, 55, 50, 45, 40],
        "automations": {"tempo": [{"measure": 0, "bpm": 120, "type": 4}]},
        "measures": [
            {"signature": [4, 4], "repeatStart": True, "repeat": 3,
             "voices": [{"beats": [{"duration": [1, 1], "notes": [
                 {"string": 5, "fret": 3}]}]}]},
            {"voices": [{"beats": [{"duration": [1, 1], "notes": [
                {"string": 5, "fret": 5}]}]}]},
        ],
    }
    tracks, timeline = songsterr_to_tracks({"parts": [part],
                                            "video_points": [1.0, 3.0, 5.0, 7.0]})
    assert timeline["measure_order"] == [0, 0, 0, 1]
    assert [note["t"] for note in tracks[0]["notes"]] == [1.0, 3.0, 5.0, 7.0]


def test_partial_video_points_anchor_the_available_prefix():
    part = {
        "automations": {"tempo": [{"measure": 0, "bpm": 120, "type": 4}]},
        "measures": [{"signature": [4, 4]}, {}, {}],
    }

    timeline = creator.build_timeline([part], [1.0, 3.0])

    assert [info["start"] for info in timeline["measure_info"]] == [1.0, 3.0, 5.0]


def test_sections_use_markers_from_any_arrangement():
    primary = {
        "automations": {"tempo": [{"measure": 0, "bpm": 120, "type": 4}]},
        "measures": [{"signature": [4, 4]}] + [{} for _ in range(3)],
    }
    marked = {"measures": [
        {"marker": {"text": "Intro 1"}}, {"marker": {"text": "Verse 1"}},
        {"marker": {"text": "Verse 2"}}, {"marker": {"text": "Chours 1"}},
    ]}

    timeline = creator.build_timeline([primary, marked])

    assert [(item["name"], item["number"]) for item in timeline["sections"]] == [
        ("intro", 1), ("verse", 1), ("verse", 2), ("chorus", 1)]


def test_youtube_download_retries_with_webm(monkeypatch, tmp_path):
    calls = []

    class FakeDownloader:
        def __init__(self, options):
            self.options = options
            calls.append(options["format"])

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _source, download):
            assert download
            if len(calls) == 1:
                raise creator.yt_dlp.utils.DownloadError("HTTP Error 403: Forbidden")
            Path(self.options["outtmpl"].replace("%(ext)s", "webm")).write_bytes(b"audio")

    import yt_dlp
    creator.yt_dlp = yt_dlp
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeDownloader)

    result = creator._download_youtube("https://youtu.be/example", tmp_path)

    assert calls == ["bestaudio[ext=m4a]/bestaudio", "bestaudio[ext=webm]/bestaudio"]
    assert result.name == "download.webm"


def test_youtube_download_falls_back_to_token_free_client(monkeypatch, tmp_path):
    calls = []

    class FakeDownloader:
        def __init__(self, options):
            self.options = options
            calls.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _source, download):
            assert download
            if len(calls) < 3:
                raise creator.yt_dlp.utils.DownloadError("HTTP Error 403: Forbidden")
            Path(self.options["outtmpl"].replace("%(ext)s", "webm")).write_bytes(b"audio")

    import yt_dlp
    creator.yt_dlp = yt_dlp
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeDownloader)

    result = creator._download_youtube("https://youtu.be/example", tmp_path)

    assert calls[-1]["extractor_args"] == {
        "youtube": {"player_client": ["android_vr"]}}
    assert result.name == "download.webm"


def test_youtube_download_uses_browser_token_as_final_fallback(monkeypatch, tmp_path):
    calls = []

    class FakeDownloader:
        def __init__(self, options):
            self.options = options
            calls.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _source, download):
            assert download
            if len(calls) < 4:
                raise creator.yt_dlp.utils.DownloadError("HTTP Error 403: Forbidden")
            Path(self.options["outtmpl"].replace("%(ext)s", "webm")).write_bytes(b"audio")

    import yt_dlp
    creator.yt_dlp = yt_dlp
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeDownloader)
    monkeypatch.setattr(creator, "_youtube_browser", lambda: Path("C:/Chrome/chrome.exe"))
    monkeypatch.setattr(creator, "_node_runtime", lambda: "C:/Node/node.exe")

    result = creator._download_youtube("https://youtu.be/example", tmp_path)

    assert calls[-1]["extractor_args"] == {
        "youtube": {"player_client": ["mweb"]},
        "youtubepot-wpc": {"browser_path": [str(Path("C:/Chrome/chrome.exe"))]},
    }
    assert calls[-1]["js_runtimes"] == {
        "node": {"path": "C:/Node/node.exe"}}
    assert result.name == "download.webm"


def test_drums_use_drum_tab_wire(tmp_path):
    part = {
        "title": "Drums", "instrument": "Drums",
        "automations": {"tempo": [{"measure": 0, "position": 0, "bpm": 120, "type": 4}]},
        "measures": [{"signature": [4, 4], "voices": [{"beats": [
            {"duration": [1, 4], "velocity": "fff", "notes": [
                {"fret": 36, "string": 3.5}, {"fret": 42, "string": -0.5, "ghost": True}]},
            {"duration": [3, 4], "notes": []},
        ]}]}],
    }
    tracks, timeline = songsterr_to_tracks({"parts": [part]})
    assert [(hit["p"], hit["v"], hit.get("g", False)) for hit in tracks[0]["hits"]] == [
        ("hh_closed", 127, True), ("kick", 127, False)]

    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"OggS-test")
    output = tmp_path / "drums.feedpak"
    write_feedpak(tracks, timeline, audio, output, title="Root", artist="Deftones")
    with zipfile.ZipFile(output) as archive:
        manifest = archive.read("manifest.yaml").decode()
        drum_tab = json.loads(archive.read("drum_tab_drums.json"))
        assert "type: drums" in manifest and "drum_tab: drum_tab_drums.json" in manifest
        assert "file: arrangements/drums.json" not in manifest
        assert "arrangements/drums.json" not in archive.namelist()
        assert len(drum_tab["hits"]) == 2


def test_drums_expand_rolls_and_preserve_playable_articulations():
    part = {
        "title": "Drums", "instrument": "Drums",
        "automations": {"tempo": [{"measure": 0, "bpm": 120, "type": 4}]},
        "measures": [{"signature": [4, 4], "voices": [{"beats": [
            {"duration": [1, 4], "tremolo": [1, 8],
             "notes": [{"fret": 38, "accentuated": 1}]},
            {"duration": [1, 64], "graceNote": "beforeBeat",
             "notes": [{"fret": 45}]},
            {"duration": [1, 4], "notes": [{"fret": 45}]},
            {"duration": [1, 4], "notes": [{"fret": 46, "tie": True}]},
            {"duration": [1, 4], "text": {"text": "Max stax"},
             "notes": [{"fret": 55, "staccato": True}]},
        ]}]}],
    }

    tracks, _timeline = songsterr_to_tracks({"parts": [part]})

    assert tracks[0]["hits"] == [
        {"t": 0.0, "p": "snare", "v": 116},
        {"t": 0.25, "p": "snare", "v": 116},
        {"t": 0.5, "p": "tom_mid", "v": 100, "f": True},
        {"t": 1.5, "p": "stack", "v": 100, "k": 0.08},
    ]


def test_drum_crescendo_becomes_increasing_velocity():
    measures = [{"voices": [{"beats": [
        {"duration": [1, 4], "gradualVelocity": "crescendo"},
        {"duration": [1, 4], "gradualVelocity": "crescendo"},
        {"duration": [1, 2], "velocity": "fff"},
    ]}]}]

    velocities = creator._drum_velocities(measures)

    assert velocities[(0, 0, 0)] < velocities[(0, 0, 1)] == 127


def test_standalone_feedpak(tmp_path):
    part = {
        "title": "Lead Guitar", "instrument": "Electric Guitar", "strings": 6,
        "tuning": [64, 59, 55, 50, 45, 40],
        "automations": {"tempo": [
            {"measure": 0, "position": 0, "bpm": 120, "type": 4},
            {"measure": 2, "position": 0, "bpm": 60, "type": 4},
        ]},
        "measures": [
            {"signature": [4, 4], "voices": [{"beats": [
                {"duration": [1, 4], "palmMute": True, "notes": [
                    {"string": 5, "fret": 0}, {"string": 4, "fret": 2},
                    {"string": 3, "fret": 2}]},
                {"duration": [1, 4], "notes": [{"string": 5, "dead": True}]},
                {"duration": [1, 4], "notes": [{"string": 4, "fret": 3, "ghost": True}]},
                {"duration": [1, 4], "notes": []},
            ]}]},
            {"voices": [{"beats": [
                {"duration": [1, 1], "notes": [{"string": 5, "fret": 5}]},
            ]}]},
            {"signature": [3, 4], "voices": [{"beats": [
                {"duration": [1, 4], "notes": [{"string": 5, "fret": 5, "tie": True}]},
                {"duration": [1, 2], "notes": []},
            ]}]},
        ],
    }
    tracks, timeline = songsterr_to_tracks({"parts": [part]})
    track = tracks[0]
    assert len(track["chords"]) == len(track["templates"]) == 1
    assert next(note for note in track["notes"] if note["t"] == 2.0)["sus"] == 3.0
    assert track["templates"][0]["name"] == "E5"
    assert all(note["pm"] for note in track["chords"][0]["notes"])
    assert track["notes"][0]["mt"] is True
    assert track["notes"][1]["ig"] is True
    assert [item["bpm"] for item in timeline["tempos"]] == [120.0, 60.0]
    assert [item["name"] for item in timeline["sections"]] == ["intro"]

    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"OggS-test")
    cover = tmp_path / "art.jpg"
    cover.write_bytes(b"\xff\xd8" + b"cover" * 300)
    output = tmp_path / "test.feedpak"
    track["role"] = "lead"
    write_feedpak(tracks, timeline, audio, output, title="Flying", artist="Anathema",
                  album="Judgement", year=1999, genres=["Progressive Rock"],
                  authors=[{"name": "Charter", "role": "transcriber"}], cover_path=cover)

    with zipfile.ZipFile(output) as archive:
        manifest = archive.read("manifest.yaml").decode()
        wire = json.loads(archive.read("arrangements/lead.json"))
        saved_timeline = json.loads(archive.read("song_timeline.json"))
        assert "feedpak_version: 1.19.0" in manifest
        assert "source: songsterr" in manifest
        assert "type: lead" in manifest and "cover: cover.jpg" in manifest
        assert "album: Judgement" in manifest and "year: 1999" in manifest
        assert archive.read("cover.jpg").startswith(b"\xff\xd8")
        assert "templates" in wire and "handshapes" in wire
        assert "chordTemplates" not in wire and "handShapes" not in wire
        assert len(saved_timeline["sections"]) == 1


def test_mid_measure_linear_tempo_ramp_times_notes_without_rejecting_tab():
    part = {
        "title": "Lead", "instrument": "Guitar", "strings": 6,
        "tuning": [64, 59, 55, 50, 45, 40],
        "automations": {"tempo": [
            {"measure": 0, "position": 0, "bpm": 120, "type": 4, "linear": True},
            {"measure": 0, "position": 0.5, "bpm": 60, "type": 4},
        ]},
        "measures": [{"signature": [4, 4], "voices": [{"beats": [
            {"duration": [1, 2], "notes": [{"string": 5, "fret": 3}]},
            {"duration": [1, 2], "notes": [{"string": 5, "fret": 5}]},
        ]}]}],
    }

    tracks, timeline = songsterr_to_tracks({"parts": [part]})

    assert abs(tracks[0]["notes"][1]["t"] - 1.386294) < 0.00001
    assert abs(timeline["duration"] - 3.386294) < 0.00001
    assert timeline["tempos"] == [
        {"time": 0.0, "bpm": 120.0},
        {"time": 1.386294, "bpm": 60.0},
    ]


def test_songsterr_bend_curves_vibrato_and_tied_techniques_are_preserved():
    part = {
        "title": "Lead", "instrument": "Guitar", "strings": 6,
        "tuning": [64, 59, 55, 50, 45, 40],
        "automations": {"tempo": [{"measure": 0, "bpm": 120, "type": 4}]},
        "measures": [{"signature": [4, 4], "voices": [{"beats": [
            {"duration": [1, 4], "notes": [{
                "string": 1, "fret": 7, "leftHandVibrato": "slight",
                "bend": {"tone": 100, "points": [
                    {"position": 0, "tone": 0},
                    {"position": 30, "tone": 100},
                    {"position": 60, "tone": 0},
                ]},
            }]},
            {"duration": [1, 4], "notes": [{
                "string": 1, "fret": 7, "tie": True,
                "bend": {"tone": 50, "points": [
                    {"position": 0, "tone": 0},
                    {"position": 60, "tone": 50},
                ]},
            }]},
            {"duration": [1, 2], "notes": []},
        ]}]}],
    }

    tracks, _timeline = songsterr_to_tracks({"parts": [part]})
    note = tracks[0]["notes"][0]

    assert note["vb"] is True
    assert note["bn"] == 2.0
    assert "bt" not in note  # the merged curve is authoritative and has no single bend intent
    assert note["bnv"] == [
        {"t": 0.0, "v": 0.0}, {"t": 0.2375, "v": 2.0},
        {"t": 0.475, "v": 0.0}, {"t": 0.5, "v": 0.0},
        {"t": 1.0, "v": 1.0},
    ]


def test_slide_in_is_not_misread_as_a_slide_to_the_next_note():
    part = {
        "title": "Lead", "instrument": "Guitar", "strings": 6,
        "tuning": [64, 59, 55, 50, 45, 40],
        "automations": {"tempo": [{"measure": 0, "bpm": 120, "type": 4}]},
        "measures": [{"signature": [4, 4], "voices": [{"beats": [
            {"duration": [1, 4], "notes": [{"string": 1, "fret": 7, "slide": "below"}]},
            {"duration": [1, 4], "notes": [{"string": 1, "fret": 9}]},
            {"duration": [1, 2], "notes": []},
        ]}]}],
    }

    tracks, _timeline = songsterr_to_tracks({"parts": [part]})

    assert "sl" not in tracks[0]["notes"][0]


def test_lrc_is_written_as_native_feedpak_lyrics(tmp_path):
    lrc = tmp_path / "lyrics.lrc"
    lrc.write_text("[ar:Band]\n[00:01.50]First line\n[00:04.00][00:08.00]Again", encoding="utf-8")
    lyrics = creator.parse_lrc(lrc)
    assert lyrics == [
        {"t": 1.5, "w": "First line+", "d": 2.5},
        {"t": 4.0, "w": "Again+", "d": 4.0},
        {"t": 8.0, "w": "Again+", "d": 2.0},
    ]

    part = {
        "title": "Lead", "instrument": "Guitar", "strings": 6,
        "tuning": [64, 59, 55, 50, 45, 40],
        "automations": {"tempo": [{"measure": 0, "bpm": 120, "type": 4}]},
        "measures": [{"signature": [4, 4], "voices": [{"beats": [
            {"duration": [1, 1], "notes": [{"string": 5, "fret": 0}]},
        ]}]}],
    }
    tracks, timeline = creator.songsterr_to_tracks({"parts": [part]})
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"OggS-test")
    output = tmp_path / "lyrics.feedpak"
    creator.write_feedpak(
        tracks, timeline, audio, output, title="Song", artist="Band", lyrics=lyrics)
    with zipfile.ZipFile(output) as archive:
        manifest = archive.read("manifest.yaml").decode()
        assert "lyrics: lyrics.json" in manifest and "lyrics_source: user" in manifest
        assert json.loads(archive.read("lyrics.json")) == lyrics
