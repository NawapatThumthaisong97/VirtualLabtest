"""
BillingExportService
บริการสำหรับการสร้างและส่งออกรายงานค่าใช้จ่ายในรูปแบบ CSV และ PDF
บังคับใช้มาตรการ Strict Anonymity โดยไม่เปิดเผยข้อมูลส่วนบุคคล (ชื่อ, นามสกุล, อีเมล) อย่างเด็ดขาด
"""

import csv
from datetime import datetime, timezone
import io
from typing import Any

from app.schemas.billing_schema import BillingItem


class BillingExportService:
    """Service สำหรับสร้างไฟล์รายงาน CSV และ PDF พร้อมการปกปิดตัวตนอย่างเข้มงวด"""

    @staticmethod
    def generate_csv(
        title: str,
        group_by: str,
        items: list[BillingItem],
        total_cost_thb: float,
    ) -> bytes:
        """
        สร้างไฟล์ CSV สำหรับรายงานค่าใช้จ่าย
        ใช้ UTF-8 พร้อม BOM (\ufeff) เพื่อให้ Microsoft Excel และโปรแกรม Spreadsheet เปิดอ่านได้อย่างถูกต้อง
        """
        output = io.StringIO()
        # เขียน UTF-8 BOM
        output.write("\ufeff")

        writer = csv.writer(output)

        # Header metadata
        writer.writerow(["# REPORT TITLE", title])
        writer.writerow(["# GROUPED BY", group_by.upper()])
        writer.writerow(["# GENERATED AT", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")])
        writer.writerow(["# TOTAL COST (THB)", f"{total_cost_thb:,.2f}"])
        writer.writerow(["# PRIVACY NOTICE", "STRICT ANONYMIZED REPORT - NO PII INCLUDED"])
        writer.writerow([])  # บรรทัดว่างคั่น

        # Table Headers
        writer.writerow([
            "Group Key",
            "Description",
            "Total Sessions",
            "CPU Hours",
            "GPU Hours",
            "RAM (MB-Hours)",
            "Total Cost (THB)",
        ])

        # Data Rows
        for item in items:
            writer.writerow([
                item.group_key,
                item.group_name or item.group_key,
                item.total_sessions,
                f"{item.total_cpu_hours:.2f}",
                f"{item.total_gpu_hours:.2f}",
                f"{item.total_ram_mb_hours:.2f}",
                f"{item.total_cost_thb:.2f}",
            ])

        # Summary Row
        writer.writerow([])
        writer.writerow([
            "TOTAL",
            "All Aggregated Records",
            sum(item.total_sessions for item in items),
            f"{sum(item.total_cpu_hours for item in items):.2f}",
            f"{sum(item.total_gpu_hours for item in items):.2f}",
            f"{sum(item.total_ram_mb_hours for item in items):.2f}",
            f"{total_cost_thb:.2f}",
        ])

        return output.getvalue().encode("utf-8")

    @staticmethod
    def generate_pdf(
        title: str,
        group_by: str,
        items: list[BillingItem],
        total_cost_thb: float,
    ) -> bytes:
        """
        สร้างไฟล์ PDF 1.4 สำหรับรายงานค่าใช้จ่ายสำหรับฝ่ายบริหาร
        ใช้โครงสร้าง PDF มาตรฐาน (Pure Python) โดยไม่ต้องพึ่งพา binary ภายนอก
        """
        # สร้างเนื้อหา text stream ใน PDF
        lines: list[str] = [
            "BT",
            "/F1 18 Tf",
            "50 780 Td",
            "(Virtual Lab - Executive Billing Report) Tj",
            "ET",
            "BT",
            "/F2 12 Tf",
            "50 755 Td",
            f"(Report Title: {title}) Tj",
            "ET",
            "BT",
            "/F2 10 Tf",
            "50 735 Td",
            f"(Grouped By: {group_by.upper()}  |  Total Cost: {total_cost_thb:,.2f} THB) Tj",
            "ET",
            "BT",
            "/F2 9 Tf",
            "50 720 Td",
            f"(Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  |  Strict Anonymity Enforced) Tj",
            "ET",
            # เส้นคั่น
            "50 710 m 550 710 l S",
            # ตาราง Header
            "BT",
            "/F1 10 Tf",
            "50 690 Td",
            "(Group Key) Tj",
            "120 0 Td",
            "(Description) Tj",
            "150 0 Td",
            "(Sessions) Tj",
            "70 0 Td",
            "(CPU Hrs) Tj",
            "70 0 Td",
            "(Cost THB) Tj",
            "ET",
            "50 682 m 550 682 l S",
        ]

        y_pos = 665
        for item in items[:25]:  # แสดงสูงสุด 25 แถวในหน้าแรก
            safe_key = str(item.group_key).replace("(", "").replace(")", "")[:18]
            safe_desc = str(item.group_name or item.group_key).replace("(", "").replace(")", "")[:24]
            lines.extend([
                "BT",
                "/F2 9 Tf",
                f"50 {y_pos} Td",
                f"({safe_key}) Tj",
                f"170 {y_pos} Td",
                f"({safe_desc}) Tj",
                f"320 {y_pos} Td",
                f"({item.total_sessions}) Tj",
                f"390 {y_pos} Td",
                f"({item.total_cpu_hours:.1f}) Tj",
                f"460 {y_pos} Td",
                f"({item.total_cost_thb:,.2f}) Tj",
                "ET",
            ])
            y_pos -= 18

        # เส้นคั่นท้ายตารางและยอดรวม
        lines.extend([
            f"50 {y_pos + 10} m 550 {y_pos + 10} l S",
            "BT",
            "/F1 10 Tf",
            f"50 {y_pos - 5} Td",
            f"(TOTAL SUMMARY: {total_cost_thb:,.2f} THB  |  Total Sessions: {sum(it.total_sessions for it in items)}) Tj",
            "ET",
            # Footer
            "BT",
            "/F2 8 Tf",
            "50 50 Td",
            "(CONFIDENTIAL - Virtual Lab Infrastructure Management System) Tj",
            "ET",
        ])

        stream_content = "\n".join(lines).encode("latin-1", errors="replace")

        # ประกอบ PDF Object แบบมาตรฐาน 1.4
        objects = []
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
            b"/Contents 4 0 R /Resources << /Font << "
            b"/F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> "
            b"/F2 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> "
            b">> >> >>"
        )
        objects.append(
            f"<< /Length {len(stream_content)} >>\nstream\n".encode("latin-1")
            + stream_content
            + b"\nendstream"
        )

        # คำนวณ byte offsets สำหรับ xref table
        header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        output = bytearray(header)
        offsets = []

        for i, obj in enumerate(objects, 1):
            offsets.append(len(output))
            output.extend(f"{i} 0 obj\n".encode("latin-1"))
            output.extend(obj)
            output.extend(b"\nendobj\n")

        xref_pos = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets:
            output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))

        output.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
        )

        return bytes(output)
