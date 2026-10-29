import { useEffect, useState } from 'react';
import GradientModal from './GradientModal';
import PrimaryButton from './PrimaryButton';
import { FormNote, inputBox, label } from './fields';
import { colors } from './theme';
import { useAuth } from '../../contexts/AuthContext';
import { coursesService } from '../../services/courses';
import { apiErrorMessage } from '../../services/labImage';
import { BACKGROUND_KEYS, BACKGROUND_PRESETS, ICON_KEYS, ICON_PRESETS } from '../../constants/coursePresets';
import type { BackgroundKey, IconKey } from '../../constants/coursePresets';

/** วิชาที่จะแก้ (ไม่ส่ง = สร้างใหม่) */
export interface EditableCourse {
  id: string;
  code: string;
  name: string;
  imageUrl: string | null;
  iconKey: IconKey | null;
  backgroundKey: BackgroundKey | null;
}

/**
 * Create Course / Course appearance — modal เดียวใช้ทั้งสร้างและแก้ (ปุ่ม appearance ในหน้าวิชาอาจารย์)
 * - สร้าง: POST /courses ผู้สร้าง (created_by จาก JWT) เป็นเจ้าของ ชื่ออาจารย์ใช้ชื่อคนที่ login (backend บังคับ แต่ mockup ไม่มีช่อง)
 * - แก้: PATCH /courses/{id} ส่งเฉพาะค่าที่เปลี่ยน
 * ไอคอน / พื้นหลังเลือกจากรูปที่มีในระบบ (coursePresets)
 */
export default function CreateCourseModal({ open, onClose, onCreated, course }: { open: boolean; onClose: () => void; onCreated: () => void; course?: EditableCourse }) {
  const { user } = useAuth();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [iconKey, setIconKey] = useState<IconKey>(ICON_KEYS[0]);
  const [backgroundKey, setBackgroundKey] = useState<BackgroundKey>(BACKGROUND_KEYS[0]);
  const [pickingIcon, setPickingIcon] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setCode(course?.code ?? '');
      setName(course?.name ?? '');
      setIconKey(course?.iconKey ?? ICON_KEYS[0]);
      setBackgroundKey(course?.backgroundKey ?? BACKGROUND_KEYS[0]);
      setPickingIcon(false);
      setError(null);
    }
  }, [open, course]);

  const approve = async () => {
    if (!code.trim() || !name.trim()) return setError('ใส่ Course code และ Course name ก่อน');
    setBusy(true);
    setError(null);
    try {
      if (course) {
        const changes: Parameters<typeof coursesService.update>[1] = {};
        if (code.trim() !== course.code) changes.code = code.trim();
        if (name.trim() !== course.name) changes.name = name.trim();
        if (iconKey !== course.iconKey) changes.iconKey = iconKey;
        if (backgroundKey !== course.backgroundKey) {
          changes.backgroundKey = backgroundKey;
          // การ์ดใช้รูปที่อัปเองก่อน preset — เลือก preset ใหม่ต้องล้างรูปที่อัปไว้ ไม่งั้นการ์ดไม่เปลี่ยน
          if (course.imageUrl) changes.imageUrl = null;
        }
        if (Object.keys(changes).length > 0) await coursesService.update(course.id, changes);
      } else {
        await coursesService.create({
          code: code.trim(),
          name: name.trim(),
          lecturerName: user?.name || user?.email || 'Instructor',
          iconKey,
          backgroundKey,
        });
      }
      onCreated();
      onClose();
    } catch (e) {
      setError(apiErrorMessage(e, course ? 'บันทึกไม่สำเร็จ' : 'สร้างวิชาไม่สำเร็จ'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <GradientModal open={open} onClose={busy ? () => {} : onClose} icon="/lab-builder/book.png" title={course ? 'Course appearance' : 'Create Course'}>
      <div style={{ padding: '28px 74px 36px', display: 'flex', flexDirection: 'column', gap: 22, fontSize: 13 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 20 }}>
          <label style={label}>
            <span>Course code</span>
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="SE301" maxLength={50} style={inputBox} />
          </label>
          <label style={label}>
            <span>Course name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Software Engineering" maxLength={255} style={inputBox} />
          </label>
        </div>

        {/* Icon Select — วงกลมแสดงตัวที่เลือก กดแล้วกางตัวเลือกจาก ICON_PRESETS */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 36 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span>Icon Select</span>
            <button type="button" onClick={() => setPickingIcon((v) => !v)} style={{ border: 0, background: 'none', padding: 0, color: colors.primary, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, textAlign: 'left' }}>
              {pickingIcon ? 'done' : 'choose icon'}
            </button>
          </div>
          <button
            type="button"
            onClick={() => setPickingIcon((v) => !v)}
            aria-label="Choose course icon"
            style={{ width: 120, height: 120, borderRadius: '50%', border: `1px solid ${colors.inputBorder}`, background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
          >
            <img src={ICON_PRESETS[iconKey]} alt="" style={{ width: 56, height: 56, objectFit: 'contain' }} />
          </button>
        </div>
        {pickingIcon && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: 14, marginTop: -8 }}>
            {ICON_KEYS.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setIconKey(key);
                  setPickingIcon(false);
                }}
                aria-pressed={iconKey === key}
                aria-label={key}
                style={{ width: 52, height: 52, borderRadius: '50%', border: `2px solid ${iconKey === key ? colors.primary : colors.inputBorder}`, background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
              >
                <img src={ICON_PRESETS[key]} alt="" style={{ width: 26, height: 26, objectFit: 'contain' }} />
              </button>
            ))}
          </div>
        )}

        {/* Background Image — เลือกจาก BACKGROUND_PRESETS ตัวที่เลือกมีขอบฟ้า */}
        <div style={label}>
          <span>Background Image</span>
          <div style={{ border: `1px solid ${colors.inputBorder}`, borderRadius: 8, padding: 12, display: 'grid', gridTemplateColumns: `repeat(${BACKGROUND_KEYS.length}, minmax(0,1fr))`, gap: 10 }}>
            {BACKGROUND_KEYS.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setBackgroundKey(key)}
                aria-pressed={backgroundKey === key}
                aria-label={key}
                style={{ height: 96, borderRadius: 6, border: `2px solid ${backgroundKey === key ? colors.primary : 'transparent'}`, backgroundImage: `url(${BACKGROUND_PRESETS[key]})`, backgroundSize: 'cover', backgroundPosition: 'center', cursor: 'pointer', boxShadow: backgroundKey === key ? '0 0 0 2px rgba(3,154,217,0.25)' : 'none' }}
              />
            ))}
          </div>
        </div>

        {error && <FormNote tone="error">{error}</FormNote>}
        <PrimaryButton onClick={approve} disabled={busy} style={{ alignSelf: 'flex-end', width: 188, height: 40, opacity: busy ? 0.6 : 1 }}>
          {busy ? 'Saving...' : 'Approve'}
        </PrimaryButton>
      </div>
    </GradientModal>
  );
}
