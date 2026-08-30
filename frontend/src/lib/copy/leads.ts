import type { LeadStatus } from "@/types/domain";

export const leadStatusLabel: Record<LeadStatus, string> = {
  recommended: "Ждёт решения", approved: "Черновик готов", contacted: "Отклик отправлен", replied: "Есть ответ",
  interview: "В процессе", won: "Выиграно", lost: "Не выбрали", skipped: "Пропущено",
};
