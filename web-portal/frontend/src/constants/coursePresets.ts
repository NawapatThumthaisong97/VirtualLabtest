import blue1 from '../assets/course-presets/blue1.jpg';
import blue2 from '../assets/course-presets/blue2.jpg';
import blue3 from '../assets/course-presets/blue3.jpg';
import blue4 from '../assets/course-presets/blue4.jpg';
import iconCloud from '../assets/course-presets/icon-cloud.png';
import iconDatabase from '../assets/course-presets/icon-database.png';
import iconLayers from '../assets/course-presets/icon-layers.png';

export const BACKGROUND_PRESETS = {
  blue1,
  blue2,
  blue3,
  blue4,
} as const;

export const ICON_PRESETS = {
  layers: iconLayers,
  database: iconDatabase,
  cloud: iconCloud,
} as const;

export type BackgroundKey = keyof typeof BACKGROUND_PRESETS;
export type IconKey = keyof typeof ICON_PRESETS;

export const BACKGROUND_KEYS = Object.keys(BACKGROUND_PRESETS) as BackgroundKey[];
export const ICON_KEYS = Object.keys(ICON_PRESETS) as IconKey[];
