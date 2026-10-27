import { useEffect, useState } from 'react';
import GradientModal from './GradientModal';
import PrimaryButton from './PrimaryButton';
import { FormNote, IllustratedTextarea, inputBox } from './fields';
import { UsersIcon } from './icons';
import { useAuth } from '../../contexts/AuthContext';
import { coursesService } from '../../services/courses';
import { apiErrorMessage } from '../../services/labImage';

/**
 * Announcement — ประกาศในวิชา
 * Announcer เป็นคนที่ login อยู่เสมอ (backend บันทึกผู้ประกาศจาก token) แสดงให้เห็นเฉย ๆ แก้ไม่ได้
 */
export default function AnnouncementModal({ open, onClose, onPosted, courseId }: { open: boolean; onClose: () => void; onPosted: () => void; courseId: string }) {
  const { user } = useAuth();
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setBody('');
      setError(null);
    }
  }, [open]);

  const approve = async () => {
    if (!body.trim()) return setError('เขียนข้อความประกาศก่อน');
    setBusy(true);
    setError(null);
    try {
      await coursesService.createAnnouncement(courseId, { message: body.trim() });
      onPosted();
      onClose();
    } catch (e) {
      setError(apiErrorMessage(e, 'ประกาศไม่สำเร็จ'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <GradientModal open={open} onClose={busy ? () => {} : onClose} icon="/lab-builder/marketing.png" title="Announcement">
      <div style={{ padding: '28px 74px 36px', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
        <span style={{ paddingLeft: 6 }}>Announcer</span>
        <div style={{ ...inputBox, display: 'flex', alignItems: 'center', gap: 30, padding: '0 18px', background: '#FAFAFA' }}>
          <UsersIcon size={20} width={1.6} />
          <span>{user?.name ?? '-'}</span>
        </div>
        <div style={{ marginTop: 10 }}>
          <IllustratedTextarea value={body} onChange={setBody} image="/lab-builder/lab-draw.png" imageWidth={86} hint="Write something here..." />
        </div>
        {error && <FormNote tone="error">{error}</FormNote>}
        <PrimaryButton onClick={approve} disabled={busy} style={{ alignSelf: 'flex-end', marginTop: 38, width: 188, height: 40, opacity: busy ? 0.6 : 1 }}>
          {busy ? 'Posting...' : 'Approve'}
        </PrimaryButton>
      </div>
    </GradientModal>
  );
}
