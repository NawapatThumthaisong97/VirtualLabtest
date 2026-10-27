import { useEffect, useState } from 'react';
import GradientModal from './GradientModal';
import PrimaryButton from './PrimaryButton';
import { FileDrop, FormNote, inputBox } from './fields';
import { BookIcon } from './icons';
import { labService } from '../../services/lab';
import type { LabSummary } from '../../services/lab';
import { apiErrorMessage } from '../../services/labImage';

/**
 * Document adding — แนบ PDF ให้ lab (เอกสารของวิชาคือเอกสารของแต่ละ lab)
 * ชื่อที่นักศึกษาเห็นในการ์ด Documents คือชื่อ lab ไฟล์ใหม่แทนไฟล์เดิมของ lab นั้น
 */
export default function DocumentModal({ open, onClose, onUploaded, labs }: { open: boolean; onClose: () => void; onUploaded: () => void; labs: LabSummary[] }) {
  const [labId, setLabId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setLabId(labs[0]?.id ?? '');
      setFile(null);
      setError(null);
    }
  }, [open, labs]);

  const selected = labs.find((lab) => lab.id === labId);

  const approve = async () => {
    if (!labId) return setError('เลือก lab ก่อน');
    if (!file) return setError('เลือกไฟล์ PDF ก่อน');
    if (!file.name.toLowerCase().endsWith('.pdf')) return setError('เอกสารต้องเป็นไฟล์ PDF');
    setBusy(true);
    setError(null);
    try {
      await labService.uploadDoc(labId, file);
      onUploaded();
      onClose();
    } catch (e) {
      setError(apiErrorMessage(e, 'อัปโหลดเอกสารไม่สำเร็จ'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <GradientModal open={open} onClose={busy ? () => {} : onClose} icon="/lab-builder/book.png" title="Document adding">
      <div style={{ padding: '28px 74px 36px', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
        <span style={{ paddingLeft: 6 }}>Lab</span>
        <div style={{ ...inputBox, display: 'flex', alignItems: 'center', gap: 30, padding: '0 18px' }}>
          <BookIcon />
          <select value={labId} onChange={(e) => setLabId(e.target.value)} style={{ flex: 1, minWidth: 0, border: 0, outline: 'none', fontFamily: 'inherit', fontSize: 13, background: 'transparent', cursor: 'pointer' }}>
            {labs.length === 0 && <option value="">ยังไม่มี lab — สร้าง lab ก่อน</option>}
            {labs.map((lab) => (
              <option key={lab.id} value={lab.id}>
                Lab {lab.orderNo} : {lab.title}
              </option>
            ))}
          </select>
        </div>
        <div style={{ marginTop: 22 }}>
          <FileDrop file={file} onFile={setFile} accept="application/pdf,.pdf" image="/lab-builder/paste.png" imageWidth={72} hint="Drop PDF here" height={246} />
        </div>
        {selected?.docUrl && <FormNote tone="info">lab นี้มีเอกสารอยู่แล้ว ไฟล์ใหม่จะแทนของเดิม</FormNote>}
        {error && <FormNote tone="error">{error}</FormNote>}
        <PrimaryButton onClick={approve} disabled={busy} style={{ alignSelf: 'flex-end', marginTop: 28, width: 188, height: 40, opacity: busy ? 0.6 : 1 }}>
          {busy ? 'Uploading...' : 'Approve'}
        </PrimaryButton>
      </div>
    </GradientModal>
  );
}
