import type { AdapterExecutionResult, ApplicationCommand } from "../contracts";

export type FillableElement = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

export interface FieldDefinition {
  key: string;
  title: string;
  selectors: readonly string[];
  labels: readonly RegExp[];
}

export const commonFields: readonly FieldDefinition[] = [
  {
    key: "cover_letter",
    title: "Текст отклика",
    selectors: ["textarea[name='cover_letter']", "textarea[name='proposal']", "textarea[name='message']", "textarea[name='description']"],
    labels: [/cover\s*letter/i, /proposal/i, /message/i, /сопроводительн/i, /текст\s+отклика/i, /сообщение/i, /описание\s+предложения/i],
  },
  {
    key: "rate",
    title: "Ставка",
    selectors: ["input[name='rate']", "input[name='price']", "input[name='amount']", "input[name='bid']"],
    labels: [/hourly\s*rate/i, /bid\s*amount/i, /your\s*rate/i, /ставк/i, /стоимост/i, /цен/i, /бюджет/i],
  },
  {
    key: "portfolio_url",
    title: "Портфолио",
    selectors: ["input[name='portfolio']", "input[name='portfolio_url']"],
    labels: [/portfolio/i, /портфолио/i, /пример.*работ/i],
  },
  {
    key: "github",
    title: "GitHub",
    selectors: ["input[name='github']", "input[autocomplete='url'][placeholder*='GitHub' i]"],
    labels: [/github/i, /репозитор/i],
  },
  {
    key: "website",
    title: "Сайт",
    selectors: ["input[name='website']", "input[name='url']"],
    labels: [/website/i, /personal\s+site/i, /сайт/i],
  },
  {
    key: "experience",
    title: "Опыт",
    selectors: ["textarea[name='experience']", "input[name='experience']"],
    labels: [/experience/i, /опыт/i, /похож.*проект/i],
  },
];

export async function fillKnownFields(
  form: Element,
  command: ApplicationCommand,
  overrides: readonly FieldDefinition[] = [],
  adapterVersion: string,
): Promise<AdapterExecutionResult> {
  const definitions = mergeDefinitions(commonFields, overrides);
  const filledFields: string[] = [];
  const used = new Set<Element>();
  for (const definition of definitions) {
    const value = command.knownAnswers[definition.key];
    if (value === undefined || value === null || value === "") continue;
    const element = findField(form, definition, used);
    if (!element) continue;
    const accepted = await setAndValidate(element, value);
    if (accepted) {
      used.add(element);
      filledFields.push(definition.title);
    }
  }

  const attentionFields = findRequiredUnknownFields(form, used);
  return {
    status: attentionFields.length ? "partially_filled" : "ready_for_review",
    adapterVersion,
    filledCount: filledFields.length,
    attentionCount: attentionFields.length,
    filledFields,
    attentionFields,
  };
}

export function findField(
  form: Element,
  definition: FieldDefinition,
  used = new Set<Element>(),
): FillableElement | null {
  for (const selector of definition.selectors) {
    const element = form.querySelector<FillableElement>(selector);
    if (isFillable(element) && !used.has(element) && isVisible(element)) return element;
  }
  const candidates = [...form.querySelectorAll<FillableElement>("input, textarea, select")];
  return candidates.find((element) => {
    if (!isFillable(element) || used.has(element) || !isVisible(element)) return false;
    const description = fieldDescription(element);
    return definition.labels.some((pattern) => pattern.test(description));
  }) ?? null;
}

export async function setAndValidate(
  element: FillableElement,
  value: string | number | boolean,
): Promise<boolean> {
  if (element instanceof HTMLSelectElement) {
    const desired = String(value).trim().toLocaleLowerCase();
    const option = [...element.options].find((item) => {
      const label = `${item.value} ${item.textContent || ""}`.trim().toLocaleLowerCase();
      return label === desired || label.includes(desired);
    });
    if (!option) return false;
    setNativeValue(element, option.value);
  } else if (element instanceof HTMLInputElement && ["checkbox", "radio"].includes(element.type)) {
    if (typeof value !== "boolean") return false;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "checked")?.set;
    setter?.call(element, value);
  } else {
    setNativeValue(element, String(value));
  }
  element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true, composed: true }));
  await nextPaint();
  if (element.getAttribute("aria-invalid") === "true") return false;
  if (element instanceof HTMLInputElement && ["checkbox", "radio"].includes(element.type)) {
    return element.checked === Boolean(value);
  }
  return element.value.trim().length > 0;
}

export function findRequiredUnknownFields(form: Element, used: Set<Element>): string[] {
  const fields = [...form.querySelectorAll<FillableElement>("input, textarea, select")];
  const names = fields.flatMap((element) => {
    if (
      used.has(element)
      || !isFillable(element)
      || !isVisible(element)
      || (!element.required && element.getAttribute("aria-required") !== "true")
      || hasValue(element)
    ) return [];
    return [humanFieldName(element)];
  });
  return [...new Set(names)].slice(0, 20);
}

export function focusFirstAttentionField(form: Element): boolean {
  const element = [...form.querySelectorAll<FillableElement>("input, textarea, select")]
    .find((field) => isFillable(field) && isVisible(field) && (field.required || field.getAttribute("aria-required") === "true") && !hasValue(field));
  if (!element) return false;
  element.scrollIntoView({ behavior: "smooth", block: "center" });
  element.focus({ preventScroll: true });
  return true;
}

export async function waitForElement(
  root: ParentNode,
  selectors: readonly string[],
  timeoutMs = 12_000,
): Promise<Element | null> {
  const existing = queryAny(root, selectors);
  if (existing) return existing;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value: Element | null) => {
      if (settled) return;
      settled = true;
      observer.disconnect();
      clearTimeout(timeout);
      resolve(value);
    };
    const observer = new MutationObserver(() => {
      const found = queryAny(root, selectors);
      if (found) finish(found);
    });
    observer.observe(root, { childList: true, subtree: true });
    const timeout = window.setTimeout(() => finish(null), timeoutMs);
  });
}

export function queryAny(root: ParentNode, selectors: readonly string[]): Element | null {
  for (const selector of selectors) {
    const element = root.querySelector(selector);
    if (element && isVisible(element)) return element;
  }
  return null;
}

export function buttonByText(root: ParentNode, patterns: readonly RegExp[]): HTMLElement | null {
  const candidates = [...root.querySelectorAll<HTMLElement>("button, a[href], [role='button']")];
  return candidates.find((element) => {
    if (!isVisible(element)) return false;
    const text = (element.textContent || "").replace(/\s+/g, " ").trim();
    return patterns.some((pattern) => pattern.test(text));
  }) ?? null;
}

function mergeDefinitions(
  base: readonly FieldDefinition[],
  overrides: readonly FieldDefinition[],
): FieldDefinition[] {
  const byKey = new Map(base.map((item) => [item.key, item]));
  for (const override of overrides) {
    const current = byKey.get(override.key);
    byKey.set(override.key, current ? {
      ...current,
      selectors: [...override.selectors, ...current.selectors],
      labels: [...override.labels, ...current.labels],
    } : override);
  }
  return [...byKey.values()];
}

function setNativeValue(element: FillableElement, value: string): void {
  const prototype = element instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : element instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  if (setter) setter.call(element, value);
  else element.value = value;
}

function fieldDescription(element: FillableElement): string {
  const idLabel = element.id ? document.querySelector<HTMLLabelElement>(`label[for="${CSS.escape(element.id)}"]`)?.textContent : "";
  const wrappingLabel = element.closest("label")?.textContent;
  return [
    idLabel,
    wrappingLabel,
    element.getAttribute("aria-label"),
    element.getAttribute("placeholder"),
    element.getAttribute("name"),
    element.getAttribute("id"),
  ].filter(Boolean).join(" ");
}

function humanFieldName(element: FillableElement): string {
  const description = fieldDescription(element).replace(/\s+/g, " ").trim();
  return description.slice(0, 100) || "Обязательное поле";
}

function hasValue(element: FillableElement): boolean {
  if (element instanceof HTMLInputElement && ["checkbox", "radio"].includes(element.type)) return element.checked;
  return element.value.trim().length > 0;
}

function isFillable(element: FillableElement | null): element is FillableElement {
  if (!element || element.disabled) return false;
  if (!(element instanceof HTMLSelectElement) && element.readOnly) return false;
  return !(element instanceof HTMLInputElement && ["hidden", "file", "submit", "button", "reset", "password"].includes(element.type));
}

function isVisible(element: Element): boolean {
  if (!(element instanceof HTMLElement)) return true;
  const style = getComputedStyle(element);
  return style.display !== "none" && style.visibility !== "hidden" && !element.hidden;
}

function nextPaint(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
}
