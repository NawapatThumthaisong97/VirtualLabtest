import { describe, expect, it } from 'vitest';
import { greetingName } from '../pages/Home';

describe('greetingName — ชื่อบนหัวหน้า home', () => {
  it.each([
    ['Sophia Davis', 'Sophia'],
    ['Dr. Kittipong Somsak', 'Dr. Kittipong'],
    ['Prof. Edgar Codd', 'Prof. Edgar'],
    ['Asst. Prof. Marisa Chandra', 'Asst. Prof. Marisa'],
    ['ผศ.ดร. สมชาย ใจดี', 'ผศ.ดร. สมชาย'],
    ['ดร. กิตติพงษ์ สมศักดิ์', 'ดร. กิตติพงษ์'],
    ['Dr.', 'Dr.'],
    ['', ''],
  ])('%s → %s', (full, expected) => {
    expect(greetingName(full)).toBe(expected);
  });
});
