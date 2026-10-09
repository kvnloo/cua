import { CursorMotionEffects, CursorEffectSetting } from "/workspace/cua-compat-4888/libs/cua-driver/typescript/src/native/cua_driver_contract.js";
const effects: CursorMotionEffects = {trail: CursorEffectSetting.On, glow: CursorEffectSetting.Off, ripple: CursorEffectSetting.Default};
CursorMotionEffects.create(effects);
