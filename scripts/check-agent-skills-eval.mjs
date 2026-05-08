import { discoverSkills, loadConfigFile, loadSkill } from "agent-skills-eval";

const config = loadConfigFile("./agent-skills-eval.yaml");
const skills = discoverSkills(config.root ?? ".", {
  include: config.include,
  exclude: config.exclude,
});

if (skills.length === 0) {
  throw new Error("No skills discovered from agent-skills-eval.yaml");
}

for (const skillRef of skills) {
  const skill = loadSkill(skillRef.dir, { strict: config.strict });
  if (skill.evals.length === 0) {
    throw new Error(`Skill ${skill.name} has no evals`);
  }
  console.log(`${skill.name}: ${skill.evals.length} evals`);
}
