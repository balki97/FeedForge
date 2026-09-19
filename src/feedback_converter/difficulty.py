"""Create native FeedPak phrase ladders when a fretted chart has no authored DD."""
from bisect import bisect_right
from copy import deepcopy
from math import ceil


def ensure_difficulty(arrangement, *, beats=(), sections=(), duration=0):
    """Mutate only phrase data; the original full chart remains authoritative."""
    if arrangement.get("type") in {"drums", "drum", "vocals"}:
        return False
    if any(len(p.get("levels", ())) > 1 for p in arrangement.get("phrases", ())):
        return False
    events = sorted(
        [(float(n["t"]), "notes", n) for n in arrangement.get("notes", ())]
        + [(float(c["t"]), "chords", c) for c in arrangement.get("chords", ())],
        key=lambda event: event[0],
    )
    if not events:
        return False
    beats = sorted(beats or arrangement.get("beats", ()), key=lambda b: b["time"])
    sections = sections or arrangement.get("sections", ())
    start = min(0.0, events[0][0])
    end = max(float(duration or 0), events[-1][0] + 0.001)
    measures = [float(b["time"]) for b in beats if b.get("measure", -1) > 0]
    boundaries = {start, end}
    boundaries.update(t for t in measures[::4] if start < t < end)
    boundaries.update(float(s["time"]) for s in sections if start < float(s["time"]) < end)
    if not measures:
        boundaries.update(start + i * 8 for i in range(1, ceil((end - start) / 8)))
    boundaries = sorted(boundaries)
    beat_times = [float(b["time"]) for b in beats]
    anchors = sorted(arrangement.get("anchors", ()), key=lambda a: a["time"])
    anchor_times = [float(a["time"]) for a in anchors]
    phrases = []
    cursor = 0
    for left, right in zip(boundaries, boundaries[1:]):
        groups = []
        while cursor < len(events) and events[cursor][0] < right:
            event = events[cursor]
            if not groups or event[0] - groups[-1][0][0] > 0.001:
                groups.append([])
            groups[-1].append(event)
            cursor += 1

        def priority(index):
            group = groups[index]
            time = group[0][0]
            # Strong beats first, then other beats, then off-beat subdivisions.
            near = bisect_right(beat_times, time)
            candidates = [i for i in (near - 1, near) if 0 <= i < len(beats)]
            beat = min(candidates, key=lambda i: abs(beat_times[i] - time)) if candidates else None
            strength = 2
            if beat is not None and abs(beat_times[beat] - time) <= 0.06:
                strength = 0 if beats[beat].get("measure", -1) > 0 else 1
            return strength, index

        # Spread the first notes across the phrase, then fill rhythmic detail.
        ranked = sorted(range(len(groups)), key=priority)
        buckets = {}
        for index in ranked:
            bucket = min(3, int(4 * (groups[index][0][0] - left) / (right - left)))
            buckets.setdefault(bucket, []).append(index)
        ranked = [bucket[depth] for depth in range(max(map(len, buckets.values()), default=0))
                  for _, bucket in sorted(buckets.items()) if depth < len(bucket)]
        depth = min(4, len(groups)) or 1
        levels = []
        for difficulty in range(depth):
            chosen = set(ranked[:ceil(len(groups) * (difficulty + 1) / depth)])
            selected = [event for i, group in enumerate(groups) if i in chosen for event in group]
            level = {"difficulty": difficulty, "notes": [], "chords": [],
                     "anchors": [], "handshapes": []}
            for _, kind, event in selected:
                level[kind].append(deepcopy(event))
            # Keep the active authored anchor at each retained event, including
            # anchors beginning before this phrase. Avoid pans to hidden notes.
            previous = None
            for time, _, _ in selected:
                index = bisect_right(anchor_times, time) - 1
                if index >= 0 and index != previous:
                    anchor = deepcopy(anchors[index])
                    anchor["time"] = time
                    level["anchors"].append(anchor)
                    previous = index
            for shape in arrangement.get("handshapes", ()):
                if any(shape["start_time"] <= time < shape["end_time"]
                       and (kind == "notes" and shape.get("arp")
                            or kind == "chords" and event.get("id") == shape.get("chord_id"))
                       for time, kind, event in selected):
                    clipped = deepcopy(shape)
                    clipped["start_time"] = max(left, shape["start_time"])
                    clipped["end_time"] = min(right, shape["end_time"])
                    level["handshapes"].append(clipped)
            levels.append(level)
        phrases.append({"start_time": left, "end_time": right,
                        "max_difficulty": depth - 1, "levels": levels})
    arrangement["phrases"] = phrases
    return True
