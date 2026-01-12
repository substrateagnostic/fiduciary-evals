"""Main evaluation runner for fiduciary stress tests.

Runs stress tests against multiple LLM providers and collects results.
"""

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .grader import Grade, GradingResult, calculate_invariant_scores, grade_response
from .invariants import Invariant
from .prompts import ALL_TESTS, StressTest, get_test_by_id

load_dotenv()
console = Console()

# Model configurations
MODELS: dict[str, dict[str, str]] = {
    # Frontier models (January 2026)
    "claude-opus-4.5": {
        "provider": "anthropic",
        "model_id": "claude-opus-4-5-20251101",
    },
    "gpt-4o-latest": {
        "provider": "openai",
        "model_id": "gpt-4o-2024-11-20",
    },
    "gemini-2.0-flash-exp": {
        "provider": "google",
        "model_id": "gemini-2.0-flash-exp",
    },
    # Previous generation (for comparison)
    "claude-sonnet-4": {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-20250514",
    },
    "claude-opus-4": {
        "provider": "anthropic",
        "model_id": "claude-opus-4-20250514",
    },
    "gpt-4o": {
        "provider": "openai",
        "model_id": "gpt-4o",
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "model_id": "gpt-4o-mini",
    },
    "gemini-2.0-flash": {
        "provider": "google",
        "model_id": "gemini-2.0-flash",
    },
}


@dataclass
class EvalRun:
    """A complete evaluation run."""

    model: str
    timestamp: str
    results: list[GradingResult]
    overall_pass_rate: float
    invariant_scores: dict[str, dict[str, float]]


async def run_anthropic(
    test: StressTest, model_id: str, api_key: str
) -> str:
    """Run a test against Anthropic's API."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    message = await client.messages.create(
        model=model_id,
        max_tokens=1024,
        system=test.system_prompt,
        messages=[{"role": "user", "content": test.user_prompt}],
    )

    return message.content[0].text


async def run_openai(
    test: StressTest, model_id: str, api_key: str
) -> str:
    """Run a test against OpenAI's API."""
    import openai

    client = openai.AsyncOpenAI(api_key=api_key)

    response = await client.chat.completions.create(
        model=model_id,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": test.system_prompt},
            {"role": "user", "content": test.user_prompt},
        ],
    )

    return response.choices[0].message.content


async def run_google(
    test: StressTest, model_id: str, api_key: str
) -> str:
    """Run a test against Google's Gemini API."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_id,
        system_instruction=test.system_prompt,
    )

    response = await asyncio.to_thread(
        model.generate_content,
        test.user_prompt,
    )

    return response.text


async def run_test(
    test: StressTest, model_name: str, model_config: dict[str, str]
) -> GradingResult | None:
    """Run a single test against a model."""
    provider = model_config["provider"]
    model_id = model_config["model_id"]

    # Get API key
    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            console.print(f"[red]Missing ANTHROPIC_API_KEY[/red]")
            return None
        response = await run_anthropic(test, model_id, api_key)
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            console.print(f"[red]Missing OPENAI_API_KEY[/red]")
            return None
        response = await run_openai(test, model_id, api_key)
    elif provider == "google":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            console.print(f"[red]Missing GOOGLE_API_KEY[/red]")
            return None
        response = await run_google(test, model_id, api_key)
    else:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        return None

    # Grade the response
    return grade_response(test, response, model_name)


async def run_all_tests(
    model_name: str,
    tests: list[StressTest] | None = None,
) -> EvalRun:
    """Run all tests against a model."""
    if model_name not in MODELS:
        raise ValueError(f"Unknown model: {model_name}")

    model_config = MODELS[model_name]
    tests = tests or ALL_TESTS
    results: list[GradingResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Running {len(tests)} tests against {model_name}...",
            total=len(tests),
        )

        for test in tests:
            try:
                result = await run_test(test, model_name, model_config)
                if result:
                    results.append(result)
                    status = "[PASS]" if result.grade == Grade.PASS else "[FAIL]"
                    progress.console.print(
                        f"  {status} {test.id}: {result.grade.value} "
                        f"({result.confidence:.0%})"
                    )
            except Exception as e:
                console.print(f"[red]Error on {test.id}: {e}[/red]")

            progress.advance(task)

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

    # Calculate scores
    passes = sum(1 for r in results if r.grade == Grade.PASS)
    overall_pass_rate = passes / len(results) if results else 0.0

    invariant_scores = calculate_invariant_scores(results)
    # Convert Invariant enum keys to strings for JSON serialization
    invariant_scores_str = {k.value: v for k, v in invariant_scores.items()}

    return EvalRun(
        model=model_name,
        timestamp=datetime.now().isoformat(),
        results=results,
        overall_pass_rate=overall_pass_rate,
        invariant_scores=invariant_scores_str,
    )


def save_results(run: EvalRun, output_dir: Path | None = None) -> Path:
    """Save evaluation results to JSON."""
    output_dir = output_dir or Path(__file__).parent.parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{run.model}.json"
    output_path = output_dir / filename

    # Convert to serializable format
    data = {
        "model": run.model,
        "timestamp": run.timestamp,
        "overall_pass_rate": run.overall_pass_rate,
        "invariant_scores": run.invariant_scores,
        "results": [
            {
                "test_id": r.test_id,
                "grade": r.grade.value,
                "confidence": r.confidence,
                "response": r.response,
                "explanation": r.explanation,
                "target_invariant": r.target_invariant.value,
            }
            for r in run.results
        ],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    return output_path


def print_summary(run: EvalRun) -> None:
    """Print a summary table of results."""
    table = Table(title=f"Fiduciary Eval Results: {run.model}")

    table.add_column("Invariant", style="cyan")
    table.add_column("Pass Rate", justify="right")
    table.add_column("Soft Fail", justify="right")
    table.add_column("Hard Fail", justify="right")
    table.add_column("Tests", justify="right")

    for invariant_name, scores in run.invariant_scores.items():
        pass_pct = f"{scores['pass_rate']:.0%}"
        soft_pct = f"{scores['soft_fail_rate']:.0%}"
        hard_pct = f"{scores['hard_fail_rate']:.0%}"
        total = str(int(scores["total_tests"]))

        table.add_row(invariant_name, pass_pct, soft_pct, hard_pct, total)

    table.add_section()
    table.add_row(
        "OVERALL",
        f"{run.overall_pass_rate:.0%}",
        "-",
        "-",
        str(len(run.results)),
        style="bold",
    )

    console.print(table)


async def run_eval(model_name: str) -> None:
    """Run evaluation for a single model."""
    console.print(f"\n[bold cyan]Running fiduciary evals for {model_name}[/bold cyan]\n")

    run = await run_all_tests(model_name)
    output_path = save_results(run)

    console.print(f"\n[green]Results saved to {output_path}[/green]\n")
    print_summary(run)


async def run_all_models() -> None:
    """Run evaluation for all configured models."""
    for model_name in MODELS:
        await run_eval(model_name)


def regrade_results(results_path: Path) -> EvalRun:
    """Re-grade existing results with the current grading logic.

    Useful when grading patterns are updated without needing to re-run API calls.
    """
    with open(results_path) as f:
        data = json.load(f)

    model_name = data["model"]
    new_results: list[GradingResult] = []

    console.print(f"\n[cyan]Re-grading {len(data['results'])} results for {model_name}[/cyan]\n")

    for result_data in data["results"]:
        test = get_test_by_id(result_data["test_id"])
        if not test:
            console.print(f"[yellow]Warning: Test {result_data['test_id']} not found[/yellow]")
            continue

        # Re-grade with current logic
        new_result = grade_response(test, result_data["response"], model_name)
        old_grade = result_data["grade"]
        new_grade = new_result.grade.value

        if old_grade != new_grade:
            console.print(
                f"  {test.id}: {old_grade} -> {new_grade} ({new_result.explanation})"
            )

        new_results.append(new_result)

    # Calculate new scores
    passes = sum(1 for r in new_results if r.grade == Grade.PASS)
    overall_pass_rate = passes / len(new_results) if new_results else 0.0
    invariant_scores = calculate_invariant_scores(new_results)
    invariant_scores_str = {k.value: v for k, v in invariant_scores.items()}

    return EvalRun(
        model=model_name,
        timestamp=datetime.now().isoformat(),
        results=new_results,
        overall_pass_rate=overall_pass_rate,
        invariant_scores=invariant_scores_str,
    )


def main():
    """Entry point for CLI."""
    import sys

    if len(sys.argv) > 1:
        model_name = sys.argv[1]
        if model_name == "--all":
            asyncio.run(run_all_models())
        elif model_name == "--regrade":
            # Re-grade all existing results
            results_dir = Path(__file__).parent.parent / "results"
            for results_file in results_dir.glob("*.json"):
                run = regrade_results(results_file)
                output_path = save_results(run)
                console.print(f"\n[green]Re-graded results saved to {output_path}[/green]\n")
                print_summary(run)
        elif model_name in MODELS:
            asyncio.run(run_eval(model_name))
        else:
            console.print(f"[red]Unknown model: {model_name}[/red]")
            console.print(f"Available models: {', '.join(MODELS.keys())}")
            console.print("Or use --regrade to re-grade existing results")
            sys.exit(1)
    else:
        console.print("[yellow]Usage: fiduciary-evals <model-name> | --all | --regrade[/yellow]")
        console.print(f"Available models: {', '.join(MODELS.keys())}")


if __name__ == "__main__":
    main()
