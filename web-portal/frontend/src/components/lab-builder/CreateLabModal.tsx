import { useEffect, useState } from 'react';
import GradientModal from './GradientModal';
import PrimaryButton from './PrimaryButton';
import { FileDrop, FormNote, IconInput, IllustratedTextarea, inputBox, label } from './fields';
import { UsersIcon } from './icons';
import { labService } from '../../services/lab';
import { MAX_ARCHIVE_BYTES, apiErrorMessage, labImageService } from '../../services/labImage';

export interface LabForm {
  name: string;
  description: string;
  expired: string;
  document: File | null;
  image: File | null;
}

const initial: LabForm = { name: '', description: '', expired: '', document: null, image: null };

// ค่าเริ่มต้นเดียวกับฟอร์ม Lab images ของเพื่อน (LabImageForm) — อาจารย์ไม่ต้องกรอกเอง
const IMAGE_DEFAULTS = {
  cpuRequirement: '2+',
  memoryRequirement: '4+',
  diskSize: 50,
  lifespanMinutes: 60,
  exposedPorts: [8080, 5173, 8443],
  entrypointScript: '/bin/bash /run.sh',
  workdir: '/workspace',
};

/** ชื่อ image ที่ registry ยอมรับ: vlab/<รหัสวิชา>-lab<ลำดับ> ตัวพิมพ์เล็ก a-z0-9 กับ - */
function repositoryFor(courseCode: string, orderNo: number) {
  const slug = courseCode.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'course';
  return `vlab/${slug}-lab${orderNo}`;
}

/** tag ใน registry เขียนทับไม่ได้ ใส่เวลาไว้ อัปซ้ำจะได้ไม่ชน */
function tagNow() {
  return `v${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '')}`;
}

/**
 * Virtual Lab Builder — สร้าง lab + เอกสาร + image ในครั้งเดียว
 * lab เป็น draft เสมอ (image ต้องสแกนผ่านก่อน) อาจารย์กด Publish ทีหลังที่แท็บ Lab reviewing
 * ลำดับ lab ไม่ต้องกรอก backend ต่อท้ายวิชาให้
 */
export default function CreateLabModal({ open, onClose, onCreated, courseId, courseCode }: { open: boolean; onClose: () => void; onCreated: () => void; courseId: string; courseCode: string }) {
  const [form, setForm] = useState<LabForm>(initial);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof LabForm>(k: K, v: LabForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open) {
      setForm(initial);
      setError(null);
    }
  }, [open]);

  const approve = async () => {
    if (!form.name.trim()) return setError('ใส่ชื่อ lab ก่อน');
    if (form.image && form.image.size > MAX_ARCHIVE_BYTES) return setError('ไฟล์ image ใหญ่เกิน 5 GB');
    if (form.document && !form.document.name.toLowerCase().endsWith('.pdf')) return setError('เอกสารต้องเป็นไฟล์ PDF');
    setError(null);

    let created = false;
    const failed: string[] = [];
    try {
      setBusy('กำลังสร้าง lab...');
      const lab = await labService.create({
        courseId,
        title: form.name.trim(),
        description: form.description.trim() || null,
        // ฟอร์มเลือกได้แค่วันที่ ให้หมดเขตสิ้นวันตามเวลาเครื่องอาจารย์
        dueAt: form.expired ? new Date(`${form.expired}T23:59:00`).toISOString() : null,
      });
      created = true;

      if (form.document) {
        setBusy('กำลังอัปโหลดเอกสาร...');
        try {
          await labService.uploadDoc(lab.id, form.document);
        } catch (e) {
          failed.push(`เอกสาร: ${apiErrorMessage(e)}`);
        }
      }

      if (form.image) {
        setBusy('กำลังเตรียมอัปโหลด image...');
        try {
          const upload = await labImageService.createUpload({
            courseId,
            repository: repositoryFor(courseCode, lab.orderNo),
            tag: tagNow(),
            fileSizeBytes: form.image.size,
            description: form.name.trim(),
            ...IMAGE_DEFAULTS,
          });
          await labImageService.uploadArchive(upload, form.image, (p) => setBusy(`กำลังอัปโหลด image ${p}%`));
          // ผูกทันทีทั้งที่ยังสแกนไม่จบ — backend ไม่ให้ publish จนกว่า image จะผ่าน
          await labService.update(lab.id, { imageId: upload.imageId });
        } catch (e) {
          failed.push(`image: ${apiErrorMessage(e)}`);
        }
      }
    } catch (e) {
      setError(apiErrorMessage(e, 'สร้าง lab ไม่สำเร็จ'));
    } finally {
      setBusy(null);
    }

    if (!created) return;
    onCreated();
    if (failed.length === 0) onClose();
    // lab สร้างแล้ว แต่บางส่วนไม่ผ่าน — เปิดค้างไว้ให้เห็นว่าอะไรต้องทำใหม่
    else setError(`สร้าง lab แล้ว แต่ ${failed.join(' / ')} — ลองเพิ่มใหม่ภายหลัง`);
  };

  return (
    <GradientModal open={open} onClose={busy ? () => {} : onClose} icon="/lab-builder/lab-container.png" iconWidth={50} title="Virtual Lab Builder" maxWidth={1120}>
      <div style={{ padding: '32px 74px 52px', display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 96, fontSize: 14 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={label}>
            <span style={{ paddingLeft: 6 }}>Lab name</span>
            <IconInput icon={<UsersIcon size={20} width={1.6} />} value={form.name} onChange={(v) => set('name', v)} placeholder="Lab name" />
          </label>

          <div style={label}>
            <span style={{ paddingLeft: 6 }}>Description</span>
            <IllustratedTextarea value={form.description} onChange={(v) => set('description', v)} image="/lab-builder/lab-draw.png" imageWidth={104} hint="Discover something new..." height={180} hintSize={12} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 16, marginTop: 6 }}>
            <label style={label}>
              <span>Expired date</span>
              <input type="date" value={form.expired} onChange={(e) => set('expired', e.target.value)} style={inputBox} />
            </label>
            <div style={label}>
              <span>Document</span>
              <DocButton file={form.document} onFile={(f) => set('document', f)} />
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span>Lab image</span>
          <FileDrop file={form.image} onFile={(f) => set('image', f)} accept=".tar" image="/lab-builder/lab-port.png" imageWidth={210} imageHeight={138} hint="Placing Tar File for image builder" height={230} />
          <p style={{ margin: '14px 0 0 4px', fontSize: 11, lineHeight: 1.5 }}>
            Please note that : Lab will take 1 hour to build up and organize , we'll send back status via email after anything is completed.
            The lab stays as a draft until the image passes the security scan, then publish it from Lab reviewing.
          </p>
          <div style={{ flex: 1 }} />
          {busy && <FormNote tone="info">{busy}</FormNote>}
          {error && <FormNote tone="error">{error}</FormNote>}
          <PrimaryButton onClick={approve} disabled={Boolean(busy)} style={{ alignSelf: 'flex-end', marginRight: 12, marginTop: 8, width: 188, height: 40, opacity: busy ? 0.6 : 1 }}>
            {busy ? 'Working...' : 'Approve'}
          </PrimaryButton>
        </div>
      </div>
    </GradientModal>
  );
}

/** ปุ่ม "search / add new" ของ Pete — เลือก PDF ได้ไฟล์เดียว */
function DocButton({ file, onFile }: { file: File | null; onFile: (f: File | null) => void }) {
  return (
    <label style={{ ...inputBox, cursor: 'pointer', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', display: 'flex', alignItems: 'center' }}>
      {file?.name ?? 'search / add new'}
      <input type="file" accept="application/pdf,.pdf" hidden onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
    </label>
  );
}
