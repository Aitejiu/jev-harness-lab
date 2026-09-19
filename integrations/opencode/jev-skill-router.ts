import { type Plugin, tool } from "@opencode-ai/plugin"

export const JevSkillRouter: Plugin = async ({ $, directory, client }) => {
  const python = `${directory}/.venv/bin/python`
  const helper = `${directory}/skill_router.py`

  await client.app.log({
    body: {
      service: "jev-skill-router",
      level: "info",
      message: "Jev skill router plugin initialized",
      extra: { helper },
    },
  })

  return {
    tool: {
      jev_route_skill: tool({
        description:
          "Find the right installed skill for a task and load its full instructions. " +
          "Use this before acting on requests that may map to a reusable skill " +
          "(Feishu/Lark operations, browser automation, TypeSafe/Jev, brainstorming, " +
          "frontend design, skill discovery, etc). Pass a short description of the " +
          "task; returns the best-matching skill instructions, or states that no " +
          "skill applies so you can proceed directly.",
        args: {
          task: tool.schema
            .string()
            .describe("Short description of what the user wants to do"),
        },
        async execute(args) {
          const proc = await $`${python} ${helper} --query ${args.task} --load`
            .quiet()
            .nothrow()
          const stdout = proc.stdout.toString().trim()
          if (proc.exitCode !== 0 || !stdout) {
            const stderr = proc.stderr.toString().trim().slice(0, 400)
            return `Skill router failed (exit ${proc.exitCode}). ${stderr || "no output"}`
          }

          let result: {
            skill: string
            confidence: number
            probability: number
            alternatives: string[]
            catalog_size: number
            path?: string
            content?: string
          }
          try {
            result = JSON.parse(stdout)
          } catch {
            return `Skill router returned invalid JSON: ${stdout.slice(0, 400)}`
          }

          if (result.skill === "none" || result.confidence < 0.5) {
            return [
              `No skill routed (best guess: ${result.skill}, confidence ${result.confidence}).`,
              `Alternatives: ${result.alternatives.join(", ") || "none"}.`,
              "Proceed without loading a skill.",
            ].join(" ")
          }

          const content = (result.content ?? "").slice(0, 60000)
          return [
            `# Routed skill: ${result.skill} (confidence ${result.confidence}, probability ${result.probability})`,
            `Catalog size: ${result.catalog_size}. Alternatives: ${result.alternatives.join(", ")}.`,
            "",
            content,
          ].join("\n")
        },
      }),
    },
  }
}
