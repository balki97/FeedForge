from construct import (
    Float32l,
    Float64l,
    If,
    Int8sl,
    Int16sl,
    Int16ul,
    Int32sl,
    Int32ul,
    PaddedString,
    Padding,
    PrefixedArray,
    Struct,
    len_,
    this,
)


def array(subcon):
    return PrefixedArray(Int32ul, subcon)


Bend = Struct("time" / Float32l, "step" / Float32l, Padding(3), "UNK" / Int8sl)

Beat = Struct(
    "time" / Float32l,
    "measure" / Int16ul,
    "beat" / Int16ul,
    "phraseIteration" / Int32ul,
    "mask" / Int32ul,
)

Phrase = Struct(
    "solo" / Int8sl,
    "disparity" / Int8sl,
    "ignore" / Int8sl,
    Padding(1),
    "maxDifficulty" / Int32ul,
    "phraseIterationLinks" / Int32ul,
    "name" / PaddedString(32, encoding="utf8"),
)

ChordTemplate = Struct(
    "mask" / Int32ul,
    "frets" / Int8sl[6],
    "fingers" / Int8sl[6],
    "notes" / Int32sl[6],
    "name" / PaddedString(32, encoding="utf8"),
)

ChordNote = Struct(
    "mask" / Int32ul[6],
    "bends" / Struct("bendValues" / Bend[32], "count" / Int32ul)[6],
    "slideTo" / Int8sl[6],
    "slideUnpitchTo" / Int8sl[6],
    "vibrato" / Int16sl[6],
)

Vocal = Struct(
    "time" / Float32l,
    "note" / Int32sl,
    "length" / Float32l,
    "lyrics" / PaddedString(48, encoding="utf8"),
)

Texture = Struct(
    "fontpath" / PaddedString(128, encoding="ascii"),
    "fontpathLength" / Int32ul,
    Padding(4),
    "width" / Int32ul,
    "height" / Int32ul,
)

BoundingBox = Struct("y0" / Float32l, "x0" / Float32l, "y1" / Float32l, "x1" / Float32l)

SymbolDef = Struct(
    "name" / PaddedString(12, encoding="utf8"),
    "outerRect" / BoundingBox,
    "innerRect" / BoundingBox,
)

Symbols = Struct(
    "header" / array(Int32sl[8]),
    "texture" / array(Texture),
    "definition" / array(SymbolDef),
)

PhraseIteration = Struct(
    "phraseId" / Int32ul,
    "time" / Float32l,
    "endTime" / Float32l,
    "difficulty" / Int32ul[3],
)

PhraseExtraInfo = Struct(
    "phraseId" / Int32ul,
    "difficulty" / Int32ul,
    "empty" / Int32ul,
    "levelJump" / Int8sl,
    "redundant" / Int16sl,
    Padding(1),
)

LinkedDiff = Struct("levelBreak" / Int32sl, "nld_phrase" / array(Int32ul))

Action = Struct("time" / Float32l, "name" / PaddedString(256, encoding="ascii"))

Event = Struct("time" / Float32l, "name" / PaddedString(256, encoding="ascii"))

Tone = Struct("time" / Float32l, "id" / Int32ul)

DNA = Struct("time" / Float32l, "id" / Int32ul)

Section = Struct(
    "name" / PaddedString(32, encoding="utf8"),
    "number" / Int32ul,
    "startTime" / Float32l,
    "endTime" / Float32l,
    "startPhraseIterationId" / Int32ul,
    "endPhraseIterationId" / Int32ul,
    "stringMask" / Int8sl[36],
)

Anchor = Struct(
    "time" / Float32l,
    "endTime" / Float32l,
    "UNK_time" / Float32l,
    "UNK_time2" / Float32l,
    "fret" / Int32sl,
    "width" / Int32sl,
    "phraseIterationId" / Int32ul,
)

AnchorExtension = Struct("time" / Float32l, "fret" / Int8sl, Padding(7))

FingerPrint = Struct(
    "chordId" / Int32ul,
    "startTime" / Float32l,
    "endTime" / Float32l,
    "UNK_startTime" / Float32l,
    "UNK_endTime" / Float32l,
)

Note = Struct(
    "mask" / Int32ul,
    "flags" / Int32ul,
    "hash" / Int32ul,
    "time" / Float32l,
    "string" / Int8sl,
    "fret" / Int8sl,
    "anchorFret" / Int8sl,
    "anchorWidth" / Int8sl,
    "chordId" / Int32ul,
    "chordNoteId" / Int32ul,
    "phraseId" / Int32ul,
    "phraseIterationId" / Int32ul,
    "fingerPrintId" / Int16ul[2],
    "nextIterNote" / Int16ul,
    "prevIterNote" / Int16ul,
    "parentPrevNote" / Int16ul,
    "slideTo" / Int8sl,
    "slideUnpitchTo" / Int8sl,
    "leftHand" / Int8sl,
    "tap" / Int8sl,
    "pickDirection" / Int8sl,
    "slap" / Int8sl,
    "pluck" / Int8sl,
    "vibrato" / Int16sl,
    "sustain" / Float32l,
    "bend_time" / Float32l,
    "bends" / array(Bend),
)

Level = Struct(
    "difficulty" / Int32ul,
    "anchors" / array(Anchor),
    "anchor_extensions" / array(AnchorExtension),
    "fingerprints" / array(FingerPrint)[2],
    "notes" / array(Note),
    "averageNotesPerIter" / array(Float32l),
    "notesInIterCountNoIgnored" / array(Int32ul),
    "notesInIterCount" / array(Int32ul),
)

Metadata = Struct(
    "maxScores" / Float64l,
    "maxNotes" / Float64l,
    "maxNotesNoIgnored" / Float64l,
    "pointsPerNote" / Float64l,
    "firstBeatLength" / Float32l,
    "startTime" / Float32l,
    "capo" / Int8sl,
    "lastConversionDateTime" / PaddedString(32, encoding="ascii"),
    "part" / Int16sl,
    "songLength" / Float32l,
    "tuning" / array(Int16sl),
    "firstNoteTime" / Float32l,
    "firstNoteTime2" / Float32l,
    "maxDifficulty" / Int32sl,
)

Song = Struct(
    "beats" / array(Beat),
    "phrases" / array(Phrase),
    "chordTemplates" / array(ChordTemplate),
    "chordNotes" / array(ChordNote),
    "vocals" / array(Vocal),
    "symbols" / If(len_(this.vocals) > 0, Symbols),
    "phraseIterations" / array(PhraseIteration),
    "phraseExtraInfos" / array(PhraseExtraInfo),
    "newLinkedDiffs" / array(LinkedDiff),
    "actions" / array(Action),
    "events" / array(Event),
    "tones" / array(Tone),
    "dna" / array(DNA),
    "sections" / array(Section),
    "levels" / array(Level),
    "metadata" / Metadata,
)
