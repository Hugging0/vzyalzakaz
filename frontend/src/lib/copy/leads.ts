import type { LeadStatus } from "@/types/domain";

export const leadStatusLabel: Record<LeadStatus, string> = {
  recommended: "Ждёт решения", approved: "Черновик готов", contacted: "Отклик отправлен", replied: "Есть ответ",
  interview: "В процессе", won: "Выиграно", lost: "Не выбрали", skipped: "Пропущено",
};

export const applicationEventLabel: Record<string, string> = {
  recommended: "Заказ добавлен в подбор",
  approved: "Черновик готов",
  proposal_ready: "Черновик подготовлен",
  proposal_updated: "Текст отклика обновлён",
  contacted: "Отклик отправлен",
  replied: "Получен ответ",
  interview: "Назначено интервью",
  won: "Заказ выигран",
  lost: "Заказ завершён без результата",
  skipped: "Заказ исключён",
};
