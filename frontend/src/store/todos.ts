export type Todo = {
  id: string;
  text: string;
  completed: boolean;
  createdAt: string;
};

export type TodoToolName = "todo_add" | "todo_list" | "todo_complete" | "todo_delete";

const STORAGE_KEY = "voxloom_todos";

function isTodo(value: unknown): value is Todo {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.id === "string" &&
    typeof item.text === "string" &&
    typeof item.completed === "boolean" &&
    typeof item.createdAt === "string"
  );
}

export function loadTodos(): Todo[] {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return [];
  try {
    const parsed: unknown = JSON.parse(stored);
    return Array.isArray(parsed) ? parsed.filter(isTodo) : [];
  } catch {
    return [];
  }
}

function saveTodos(todos: Todo[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(todos));
}

function stringArgument(arguments_: Record<string, unknown>, name: string): string | null {
  const value = arguments_[name];
  if (typeof value !== "string") return null;
  const normalized = value.split(/\s+/).join(" ").trim();
  return normalized || null;
}

export function executeTodoTool(
  name: TodoToolName,
  arguments_: Record<string, unknown>,
): Record<string, unknown> {
  const todos = loadTodos();
  if (name === "todo_list") return { ok: true, todos };

  if (name === "todo_add") {
    const text = stringArgument(arguments_, "text");
    if (!text) return { ok: false, error: "Todo text is required.", todos };
    const todo: Todo = {
      id: crypto.randomUUID(),
      text: text.slice(0, 500),
      completed: false,
      createdAt: new Date().toISOString(),
    };
    const updated = [...todos, todo];
    saveTodos(updated);
    return { ok: true, todo, todos: updated };
  }

  const todoId = stringArgument(arguments_, "todo_id");
  if (!todoId) return { ok: false, error: "Todo ID is required.", todos };
  const index = todos.findIndex((todo) => todo.id === todoId);
  if (index < 0) return { ok: false, error: `Todo ${todoId} was not found.`, todos };

  if (name === "todo_complete") {
    const updated = todos.map((todo) =>
      todo.id === todoId ? { ...todo, completed: true } : todo,
    );
    saveTodos(updated);
    return { ok: true, todo: updated[index], todos: updated };
  }

  const deleted = todos[index];
  const updated = todos.filter((todo) => todo.id !== todoId);
  saveTodos(updated);
  return { ok: true, deleted, todos: updated };
}
