/**
 * 金额 / 日期格式化（Task 032）
 *
 * 金额只做**字符串处理**：后端给的是精确的十进制字符串（"18036.00"），
 * 严禁 parseFloat / Number() 转浮点再格式化——浮点会让 0.1 + 0.2 这类误差混进金额。
 * 非法输入不猜、不补 0：返回带原值的提示文本。
 */

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

const CURRENCY_SYMBOLS = { CNY: '¥', RMB: '¥' };

/** 给整数部分（纯数字字符串）加千分位 */
function groupThousands(digits) {
  const trimmed = digits.replace(/^0+(?=\d)/, '');
  let out = '';
  for (let i = 0; i < trimmed.length; i += 1) {
    const fromRight = trimmed.length - i;
    out += trimmed[i];
    if (fromRight > 1 && fromRight % 3 === 1) out += ',';
  }
  return out;
}

/**
 * 解析十进制字符串 → { sign, int, frac } ；非法返回 null。
 * 小数位：不足 2 位补 0；超过 2 位时去掉末尾多余的 0，非零位原样保留（不四舍五入）。
 */
export function parseDecimal(value) {
  if (typeof value !== 'string' && typeof value !== 'number') return null;
  const text = String(value).trim().replace(/,/g, '');
  const match = DECIMAL.exec(text);
  if (!match) return null;
  const [, sign, int, rawFrac = ''] = match;
  let frac = rawFrac;
  while (frac.length > 2 && frac.endsWith('0')) frac = frac.slice(0, -1);
  if (frac.length < 2) frac = frac.padEnd(2, '0');
  const isZero = /^0+$/.test(int) && /^0+$/.test(frac);
  return { sign: isZero ? '' : sign, int, frac, isZero };
}

/**
 * 金额：`"18036.00"` → `¥18,036.00`；`"-756.00"` → `-¥756.00`。
 * 空值 → `未提供`；非法字符串 → `金额格式异常（原值）`。
 */
export function formatMoney(value, currency = 'CNY') {
  if (value === null || value === undefined || String(value).trim() === '') return '未提供';
  const parsed = parseDecimal(value);
  if (!parsed) return `金额格式异常（${String(value)}）`;
  const symbol = CURRENCY_SYMBOLS[String(currency || 'CNY').toUpperCase()] ?? '';
  const suffix = symbol ? '' : ` ${currency}`;
  return `${parsed.sign}${symbol}${groupThousands(parsed.int)}.${parsed.frac}${suffix}`;
}

/** 金额是否合法（供调用方决定是否显示“待核实”） */
export function isMoney(value) {
  return value !== null && value !== undefined && parseDecimal(value) !== null;
}

/**
 * 差额：同时给出正负号与文字。`rent_variance = 账单金额 − 合同应收`（后端定义），
 * 所以正数是“多计”，负数是“少计”。符号由字符串判断，不做数值运算。
 */
export function formatVariance(value, currency = 'CNY') {
  const parsed = parseDecimal(value);
  if (!parsed) return { text: formatMoney(value, currency), direction: 'unknown', label: '待核实' };
  const absolute = formatMoney(`${parsed.int}.${parsed.frac}`, currency);
  if (parsed.isZero) return { text: absolute, direction: 'none', label: '无差额' };
  if (parsed.sign === '-') return { text: `−${absolute}`, direction: 'under', label: '少计' };
  return { text: `+${absolute}`, direction: 'over', label: '多计' };
}

/** 单价等数量：不加货币符号，保留原小数（去掉超出 2 位的末尾 0） */
export function formatNumber(value) {
  const parsed = parseDecimal(value);
  if (!parsed) return value === null || value === undefined || value === '' ? '未提供' : `格式异常（${String(value)}）`;
  return `${parsed.sign}${groupThousands(parsed.int)}.${parsed.frac}`;
}

/** 日期 / 时间：只截取 ISO 字符串的日期和分钟，不做时区换算 */
export function formatDate(iso) {
  if (!iso || typeof iso !== 'string') return '未提供';
  const match = /^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?/.exec(iso);
  if (!match) return iso;
  return match[2] ? `${match[1]} ${match[2]}` : match[1];
}

/** 账期：`2026-08-01` → `2026-08` */
export function formatPeriod(dateText) {
  if (!dateText || typeof dateText !== 'string') return '未提供';
  const match = /^(\d{4})-(\d{2})/.exec(dateText);
  return match ? `${match[1]}-${match[2]}` : dateText;
}
