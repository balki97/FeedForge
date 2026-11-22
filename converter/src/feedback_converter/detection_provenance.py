"""Exact numeric SNG provenance for the experimental original-event consumer."""
from __future__ import annotations

import hashlib
import json
import math

SCHEMA = 'rs2014-sng-v1'
BOOLS = ('ho', 'po', 'hm', 'hp', 'pm', 'mt', 'vb', 'tr', 'ac', 'tp', 'ln', 'fhm', 'plk', 'slp', 'ig')
NOTE_KEYS = (
    'mask', 'flags', 'hash', 'time', 'string', 'fret', 'anchorFret', 'anchorWidth',
    'chordId', 'chordNoteId', 'phraseId', 'phraseIterationId', 'fingerPrintId',
    'nextIterNote', 'prevIterNote', 'parentPrevNote', 'slideTo', 'slideUnpitchTo',
    'leftHand', 'tap', 'pickDirection', 'slap', 'pluck', 'vibrato', 'sustain', 'bend_time',
)


def _canonical(value):
    # JavaScript JSON reserialization erases integral float syntax and negative zero.
    if type(value) is float and math.isfinite(value) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    return value


def digest(value):
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def model(value, kind):
    if kind == 'template':
        return {'name': value.get('name', ''), 'frets': list(value['frets']), 'fingers': list(value['fingers'])}
    if kind == 'chord':
        return {
            't': float(value['t']), 'id': int(value['id']), 'hd': bool(value.get('hd', False)),
            'notes': [model(item, 'member') for item in value.get('notes', [])],
        }
    output = {
        's': int(value['s']), 'f': int(value['f']), 'sus': float(value.get('sus', 0)),
        'sl': int(value.get('sl', -1)), 'slu': int(value.get('slu', -1)),
        'bn': float(value.get('bn', 0)),
        'bnv': [{'t': float(point['t']), 'v': float(point['v'])} for point in value.get('bnv', [])],
    }
    if kind == 'note':
        output['t'] = float(value['t'])
    output.update({key: bool(value.get(key, False)) for key in BOOLS})
    for key in ('rh', 'pkd', 'fg'):
        output[key] = int(value.get(key, -1))
    return output


def note_data(note):
    output = {key: list(getattr(note, key)) if key == 'fingerPrintId' else getattr(note, key) for key in NOTE_KEYS}
    output['bends'] = [{'time': float(point.time), 'step': float(point.step)} for point in note.bends]
    return output


def template_data(template):
    return {
        key: list(getattr(template, key)) if key in ('frets', 'fingers', 'notes') else getattr(template, key)
        for key in ('mask', 'frets', 'fingers', 'notes', 'name')
    }


def children_data(children):
    return dict(
        mask=list(children.mask), slideTo=list(children.slideTo),
        slideUnpitchTo=list(children.slideUnpitchTo), vibrato=list(children.vibrato),
        bends=[
            [{'time': float(point.time), 'step': float(point.step)} for point in bend.bendValues[:int(bend.count)]]
            for bend in children.bends
        ],
    )


def provenance(value, kind, data, source, profile):
    current = model(value, kind)
    return dict(
        schema=SCHEMA, kind=kind, source=source, profile=profile, model=current,
        modelSha256=digest(current), dataSha256=digest(data), data=data,
    )
