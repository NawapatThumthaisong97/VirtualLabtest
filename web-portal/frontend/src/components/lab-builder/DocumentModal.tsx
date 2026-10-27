import { useEffect, useState } from 'react';
import GradientModal from './GradientModal';
import PrimaryButton from './PrimaryButton';
import { FileDrop, FormNote, IconInput, inputBox } from './fields';
import { BookIcon } from './icons';
import { labService } from '../../services/lab';
import type { LabSummary } from '../../services/lab';
import { courseDocumentService } from '../../services/courseDocument';
import { apiErrorMessage } from '../../services/labImage';

// ค่าใน select ของตัวเลือก "ไม่ผูก lab" (id ของ lab เป็น uuid ไม่มีทางชน)
const COURSE_DOC = '';

/**
 * Document adding — รองรับสองแบบ (Pete ขอ)
 * - ไม่ผูก lab: เอกสารรวมของวิชา ตั้งชื่อเองได้ (ว่าง = ชื่อไฟล์) มีกี่ไฟล์ก็ได้
 * - ผูก lab: แนบเป็นเอกสารของ lab นั้น ชื่อที่เห็นคือชื่อ lab ไฟล์ใหม่แทนไฟล์เดิม
 */
export default function DocumentModal({ open, onClose, onUploaded, labs, courseId }: { open: boolean; onClose: () => void; onUploaded: () => void; labs: LabSummary[]; courseId: string }) {
  const [labId, setLabId] = useState(COURSE_DOC);
  const [name, setName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setLabId(COURSE_DOC);
      setName('');
      setFile(null);
      setError(null);
    }
  }, [open]);

  const selected = labs.find((lab) => lab.id === labId);

  const approve = async () => {
    if (!file) return setError('เลือกไฟล์ PDF ก่อน');
    if (!file.name.toLowerCase().endsWith('.pdf')) return setError('เอกสารต้องเป็นไฟล์ PDF');
    setBusy(true);
    setError(null);
    try {
      if (labId === COURSE_DOC) await courseDocumentService.upload(courseId, file, name.trim());
      else await labService.uploadDoc(labId, file);
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
        <span style={{ paddingLeft: 6 }}>Attach to</span>
        <div style={{ ...inputBox, display: 'flex', alignItems: 'center', gap: 30, padding: '0 18px' }}>
          <BookIcon />
          <select value={labId} onChange={(e) => setLabId(e.target.value)} style={{ flex: 1, minWidth: 0, border: 0, outline: 'none', fontFamily: 'inherit', fontSize: 13, background: 'transparent', cursor: 'pointer' }}>
            <option value={COURSE_DOC}>Course document (no lab)</option>
            {labs.map((lab) => (
              <option key={lab.id} value={lab.id}>
                Lab {lab.orderNo} : {lab.title}
              </option>
            ))}
          </select>
        </div>
        {labId === COURSE_DOC && (
          <>
            <span style={{ paddingLeft: 6, marginTop: 14 }}>Document name</span>
            <IconInput icon={<BookIcon />} value={name} onChange={setName} placeholder={file ? file.name.replace(/\.pdf$/i, '') : 'Document name'} />
          </>
        )}
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
