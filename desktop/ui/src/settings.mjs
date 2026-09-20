export const api = window.feedbackConverter;
export const INSPECTION_WORKERS = 2;
export const QUEUE_RENDER_LIMIT = 500;
export const AUTO_SETTING = "auto";
export const DEFAULT_CONVERSION_WORKERS = AUTO_SETTING;
export const DEFAULT_DEMUCS_STEM_JOBS = AUTO_SETTING;
export const SETTINGS_KEY = "feedforge:desktop-settings";
export const DEFAULT_DEMUCS_STEMS = ["guitar", "bass", "drums", "vocals", "other"];
export const DEMUCS_STEM_OPTIONS = [
  { id: "guitar", label: "Guitar" },
  { id: "bass", label: "Bass" },
  { id: "drums", label: "Drums" },
  { id: "vocals", label: "Vocals" },
  { id: "piano", label: "Piano" },
  { id: "other", label: "Other" }
];
export const DEFAULT_AUDIT_CRITERIA = {
  requireSpecValidation: true,
  requireCover: true,
  requireFullStem: true,
  requireSplitStems: false,
  requireBass: false,
  requireGuitar: false,
  requireLyrics: false,
  requireAuthors: false,
  requireTones: false,
  checkDuplicates: false
};
export const AUDIT_CRITERIA_OPTIONS = [
  { key: "requireSpecValidation", label: "Spec valid" },
  { key: "requireCover", label: "Cover" },
  { key: "requireFullStem", label: "Full mix" },
  { key: "requireSplitStems", label: "Split stems" },
  { key: "requireBass", label: "Bass" },
  { key: "requireGuitar", label: "Guitar" },
  { key: "requireLyrics", label: "Lyrics" },
  { key: "requireAuthors", label: "Credits" },
  { key: "requireTones", label: "Tones" },
  { key: "checkDuplicates", label: "Duplicates" }
];
