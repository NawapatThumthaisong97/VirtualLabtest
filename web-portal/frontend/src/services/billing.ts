/**
 * Billing Service
 * Interacts with backend billing aggregation and export APIs.
 * Enforces strict anonymity and executive-ready reporting.
 */
import apiClient, { API_URL } from './api';
import type { ApiResponse } from './monitor';

export type BillingGroupBy = 'course' | 'cluster' | 'nat_subnet' | 'anon_id';

export interface BillingItem {
  groupKey: string;
  groupName: string;
  totalSessions: number;
  totalCpuHours: number;
  totalGpuHours: number;
  totalRamMbHours: number;
  totalCostThb: number;
  isCloud?: boolean | null;
  courseId?: string | null;
  natSubnet?: string | null;
  anonId?: string | null;
}

export interface BillingSummaryResponse {
  groupBy: BillingGroupBy;
  totalCostThb: number;
  totalSessions: number;
  totalCpuHours: number;
  totalGpuHours: number;
  totalRamMbHours: number;
  items: BillingItem[];
}

export interface BillingReportItem {
  id: string;
  title: string;
  groupBy: string;
  exportFormat: string;
  fileName: string;
  totalCostThb: number;
  totalRecords: number;
  createdAt: string;
  createdBy: string;
  isDeleted: boolean;
}

export interface BillingReportListResponse {
  reports: BillingReportItem[];
  total: number;
}

export interface BillingFilterParams {
  groupBy?: BillingGroupBy;
  startDate?: string;
  endDate?: string;
  courseId?: string;
  isCloud?: boolean;
}

export const billingService = {
  /**
   * ดึงยอดสรุปค่าใช้จ่ายจาก usage_records จัดกลุ่มตาม course, cluster, nat_subnet, หรือ anon_id
   */
  getSummary: async (params?: BillingFilterParams): Promise<BillingSummaryResponse> => {
    const query = new URLSearchParams();
    if (params?.groupBy) query.set('group_by', params.groupBy);
    if (params?.startDate) query.set('start_date', params.startDate);
    if (params?.endDate) query.set('end_date', params.endDate);
    if (params?.courseId) query.set('course_id', params.courseId);
    if (params?.isCloud !== undefined) query.set('is_cloud', String(params.isCloud));

    const qs = query.toString() ? `?${query.toString()}` : '';
    const res = await apiClient.get<ApiResponse<BillingSummaryResponse>>(`/v1/billings${qs}`);
    return (res as unknown as ApiResponse<BillingSummaryResponse>).data;
  },

  /**
   * ดึงประวัติการส่งออกรายงานค่าใช้จ่าย (Soft-Deleted items are excluded)
   */
  getReports: async (limit = 50, offset = 0): Promise<BillingReportListResponse> => {
    const res = await apiClient.get<ApiResponse<BillingReportListResponse>>(
      `/v1/billings/reports?limit=${limit}&offset=${offset}`
    );
    return (res as unknown as ApiResponse<BillingReportListResponse>).data;
  },

  /**
   * ส่งออกรายงานเป็น CSV (UTF-8 with BOM) หรือ PDF สำหรับฝ่ายบริหาร
   */
  exportReport: async (
    format: 'csv' | 'pdf',
    params?: BillingFilterParams
  ): Promise<{ blob: Blob; fileName: string }> => {
    const query = new URLSearchParams();
    query.set('format', format);
    if (params?.groupBy) query.set('group_by', params.groupBy);
    if (params?.startDate) query.set('start_date', params.startDate);
    if (params?.endDate) query.set('end_date', params.endDate);
    if (params?.courseId) query.set('course_id', params.courseId);
    if (params?.isCloud !== undefined) query.set('is_cloud', String(params.isCloud));

    const response = await fetch(`${API_URL}/v1/billings/exports?${query.toString()}`, {
      method: 'GET',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to export report: ${response.statusText}`);
    }

    const disposition = response.headers.get('content-disposition');
    let fileName = `billing_report_${params?.groupBy || 'course'}_${new Date().toISOString().slice(0, 10)}.${format}`;
    if (disposition && disposition.includes('filename=')) {
      const match = disposition.match(/filename="?([^";]+)"?/);
      if (match && match[1]) {
        fileName = match[1];
      }
    }

    const blob = await response.blob();
    return { blob, fileName };
  },

  /**
   * สั่งดาวน์โหลดไฟล์เข้าเครื่องไคลเอนต์โดยตรง
   */
  downloadReport: async (format: 'csv' | 'pdf', params?: BillingFilterParams): Promise<string> => {
    const { blob, fileName } = await billingService.exportReport(format, params);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    return fileName;
  },
};
