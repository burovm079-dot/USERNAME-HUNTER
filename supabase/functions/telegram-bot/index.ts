const BOT_TOKEN = Deno.env.get("BOT_TOKEN")!;
const ADMIN_ID = Deno.env.get("ADMIN_ID")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SECRET_KEY = Deno.env.get("SUPABASE_SECRET_KEY")!;
const WEBHOOK_SECRET = Deno.env.get("WEBHOOK_SECRET")!;

const corsHeaders = { "content-type": "application/json" };

async function telegram(method: string, payload: Record<string, unknown>) {
  const response = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    console.error("Telegram API error", method, data);
    throw new Error(`Telegram API request failed: ${method}`);
  }
  return data.result;
}

async function sendMessage(chatId: number | string, text: string) {
  return telegram("sendMessage", { chat_id: chatId, text });
}

async function db(path: string) {
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: {
      apikey: SUPABASE_SECRET_KEY,
      authorization: `Bearer ${SUPABASE_SECRET_KEY}`,
      accept: "application/json",
      prefer: "count=exact",
    },
  });
  if (!response.ok) {
    console.error("Supabase read failed", response.status, await response.text());
    throw new Error("Database read failed");
  }
  const range = response.headers.get("content-range");
  const count = range?.split("/")[1];
  return { rows: await response.json(), count: count && count !== "*" ? Number(count) : 0 };
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ ok: true, service: "USERNAME HUNTER webhook" }), { headers: corsHeaders });
  }

  if (req.headers.get("x-telegram-bot-api-secret-token") !== WEBHOOK_SECRET) {
    return new Response("Unauthorized", { status: 401 });
  }

  try {
    const update = await req.json();
    const message = update.message;
    if (!message?.text || !message.chat?.id) {
      return new Response(JSON.stringify({ ok: true }), { headers: corsHeaders });
    }

    const chatId = message.chat.id;
    const userId = String(message.from?.id ?? "");
    const command = message.text.trim().split(/\s+/)[0].split("@")[0].toLowerCase();

    if (command === "/myid") {
      await sendMessage(chatId, `Твой Telegram ID: ${userId}`);
      return new Response(JSON.stringify({ ok: true }), { headers: corsHeaders });
    }

    if (userId !== ADMIN_ID) {
      await sendMessage(chatId, "⛔ Доступ только владельцу.");
      return new Response(JSON.stringify({ ok: true }), { headers: corsHeaders });
    }

    if (command === "/start") {
      await sendMessage(chatId,
        "USERNAME HUNTER\n" +
        "/myid — показать Telegram ID\n" +
        "/scan — информация о фоновом поиске\n" +
        "/status — статистика\n" +
        "/list — последние непроверенные кандидаты\n\n" +
        "⚠️ Bot API не может подтвердить, что username свободен. «Не найдено» не означает «свободно»."
      );
    } else if (command === "/scan") {
      await sendMessage(chatId,
        "🔎 Фоновый поиск выполняется GitHub Actions примерно каждые 5 минут.\n" +
        "Каждый запуск проверяет до 20 кандидатов. Команда не запускает отдельный непрерывный процесс.\n" +
        "⚠️ Результаты Bot API не подтверждают свободный username."
      );
    } else if (command === "/status") {
      const [all, publicChats, unverified] = await Promise.all([
        db("checked_usernames?select=username"),
        db("checked_usernames?select=username&status=eq.public_chat_found"),
        db("checked_usernames?select=username&status=eq.not_found_unverified"),
      ]);
      await sendMessage(chatId,
        "📊 USERNAME HUNTER\n" +
        `Всего записей: ${all.count}\n` +
        `Публичный чат найден: ${publicChats.count}\n` +
        `Не найдено через Bot API (не значит свободно): ${unverified.count}\n` +
        "Фоновый запуск: примерно раз в 5 минут."
      );
    } else if (command === "/list") {
      const result = await db("checked_usernames?select=username,checked_at&status=eq.not_found_unverified&order=checked_at.desc&limit=20");
      const rows = result.rows as Array<{ username: string; checked_at: string }>;
      if (!rows.length) {
        await sendMessage(chatId, "Пока нет таких результатов.");
      } else {
        const lines = rows.map((row) => `@${row.username} — ${String(row.checked_at).slice(0, 16)}`);
        await sendMessage(chatId,
          "🔎 Не найдено через Bot API (это НЕ список свободных имён):\n" + lines.join("\n")
        );
      }
    } else if (command === "/stop") {
      await sendMessage(chatId,
        "ℹ️ Отдельный постоянный поиск не запущен. GitHub Actions выполняет автоматические проверки примерно раз в 5 минут. Остановить расписание можно в GitHub Actions."
      );
    }
    return new Response(JSON.stringify({ ok: true }), { headers: corsHeaders });
  } catch (error) {
    console.error(error);
    return new Response(JSON.stringify({ ok: false }), { status: 200, headers: corsHeaders });
  }
});
