import { describe, expect, it, vi } from "vitest";

import { fillKnownFields } from "../src/adapters/form";
import { adapterForId, adapterForUrl, adapters } from "../src/adapters/marketplaces";
import { validateCommand } from "../src/command";
import type { ApplicationCommand } from "../src/contracts";

function command(answers: ApplicationCommand["knownAnswers"]): ApplicationCommand {
  return {
    id: "command-id",
    applicationId: 1,
    sourceId: "freelancer_com",
    jobUrl: "https://www.freelancer.com/projects/python/example",
    coverLetter: String(answers.cover_letter || ""),
    selectedPortfolioCase: null,
    knownAnswers: answers,
    attachments: [],
    metadata: { jobTitle: "API", sourceName: "Freelancer", requiresConfirmation: true, canSubmit: false },
    status: "delivered",
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
    result: { filledCount: 0, attentionCount: 0, filledFields: [], attentionFields: [] },
    error: null,
  };
}

describe("marketplace adapter registry", () => {
  it("selects only exact supported HTTPS hosts", () => {
    expect(adapterForUrl(new URL("https://www.freelancer.com/projects/1"))?.id).toBe("freelancer_com");
    expect(adapterForUrl(new URL("https://freelancer.com.evil.example/projects/1"))).toBeNull();
    expect(adapterForUrl(new URL("http://freelancer.com/projects/1"))).toBeNull();
    expect(adapters.map((adapter) => adapter.id)).toEqual(["freelancer_com", "freelance_ru", "fl_ru", "kwork_projects"]);
  });

  it("keeps source-specific selectors inside its adapter", () => {
    const adapter = adapterForId("fl_ru");
    expect(adapter?.supports(new URL("https://www.fl.ru/projects/123"))).toBe(true);
    expect(adapter?.getCapabilities()).toContain("requires_confirmation");
    expect(adapter?.getCapabilities()).not.toContain("browser_submit");
  });
});

describe("application command validation", () => {
  it("rejects expired commands and source/url mismatches", () => {
    const expired = command({ cover_letter: "Текст" });
    expired.expiresAt = new Date(Date.now() - 1_000).toISOString();
    expect(validateCommand(expired)).toMatchObject({ ok: false, code: "COMMAND_EXPIRED" });

    const mismatch = command({ cover_letter: "Текст" });
    mismatch.jobUrl = "https://kwork.ru/projects/1";
    expect(validateCommand(mismatch)).toMatchObject({ ok: false, code: "UNSUPPORTED_SOURCE" });
  });

  it("returns the adapter for a valid command", () => {
    expect(validateCommand(command({ cover_letter: "Текст" }))).toMatchObject({
      ok: true,
      adapter: { id: "freelancer_com" },
    });
  });
});

describe("semantic form filling", () => {
  it("detects authentication and executes the selected adapter on fixture HTML", async () => {
    const adapter = adapterForId("freelancer_com")!;
    document.body.innerHTML = `<a href="/login">Log in</a>`;
    let active = command({ cover_letter: "Текст", rate: 25_000 });
    let context = { command: active, document, url: new URL(active.jobUrl) };
    expect(adapter.detectAuthState(context)).toBe("AUTH_REQUIRED");

    document.body.innerHTML = `
      <a href="/dashboard" data-testid="user-menu">Profile</a>
      <form data-testid="bid-form">
        <textarea data-testid="bid-description" required></textarea>
        <input data-testid="bid-amount" required>
      </form>`;
    active = command({ cover_letter: "Текст", rate: 25_000 });
    context = { command: active, document, url: new URL(active.jobUrl) };
    expect(adapter.detectAuthState(context)).toBe("AUTHENTICATED");
    const form = adapter.detectApplicationForm(context)!;
    const result = await adapter.fillApplication(context, form);
    expect(result).toMatchObject({ status: "ready_for_review", filledCount: 2, attentionCount: 0 });
  });

  it("uses native setters, reports unknown required fields, and never submits", async () => {
    document.body.innerHTML = `
      <form id="application">
        <label>Текст отклика<textarea name="proposal" required></textarea></label>
        <label>Стоимость<input name="price" required></label>
        <label>Срок выполнения<input name="deadline" required></label>
        <button type="submit">Отправить</button>
      </form>`;
    const form = document.querySelector("form")!;
    const submit = vi.fn((event: Event) => event.preventDefault());
    form.addEventListener("submit", submit);

    const result = await fillKnownFields(form, command({ cover_letter: "Готов выполнить задачу", rate: 50_000 }), [], "test");

    expect((form.querySelector("textarea") as HTMLTextAreaElement).value).toBe("Готов выполнить задачу");
    expect((form.querySelector("input[name='price']") as HTMLInputElement).value).toBe("50000");
    expect(result.status).toBe("partially_filled");
    expect(result.attentionFields.some((field) => field.startsWith("Срок выполнения"))).toBe(true);
    expect(submit).not.toHaveBeenCalled();
  });

  it("stops at ready for review when every required field is known", async () => {
    document.body.innerHTML = `<form><textarea name="cover_letter" required></textarea></form>`;
    const result = await fillKnownFields(document.querySelector("form")!, command({ cover_letter: "Текст" }), [], "test");
    expect(result.status).toBe("ready_for_review");
    expect(result.filledCount).toBe(1);
    expect(result.attentionCount).toBe(0);
  });
});
