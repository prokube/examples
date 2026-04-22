"""
Lightweight debuggable component decorator for KFP.

This module provides a decorator that automatically injects debugging code
into KFP Lightweight Components, eliminating boilerplate.
"""

import ast
import inspect
import textwrap
from pathlib import Path
from typing import Callable, Literal

from kfp.dsl import component
from loguru import logger


def lightweight_debuggable_component(
    debugger_type: Literal["debugpy", "remote-pdb"] = "debugpy",
    debug_port: int = 5678,
    auto_install_packages: bool = True,
    **component_kwargs,
):
    """
    Decorator that creates KFP Lightweight Components with automatic debugging code injection.

    LIGHTWEIGHT COMPONENTS ONLY - Does not work with Container Components!

    This decorator automatically injects debugging code into your component functions,
    eliminating the need to manually add debugging boilerplate.

    Args:
        debugger_type: Type of debugger to use ("debugpy" or "remote-pdb")
        debug_port: Port for remote debugging (default: 5678)
        **component_kwargs: All arguments passed to @component decorator (base_image, packages_to_install, etc.)

    Usage:
        @lightweight_debuggable_component()
        def my_component(arg1: str, debug: bool = False) -> str:
            # Just your component logic - debugging code is auto-injected!
            return result

        # With remote pdb and base image:
        @lightweight_debuggable_component(
            base_image="my-custom:latest",
            debugger_type="remote-pdb",
            debug_port=4444
        )
        def my_component(debug: bool = False) -> str:
            return "result"
    """

    def decorator(func: Callable) -> Callable:
        # Validate that the wrapped function has a `debug` parameter
        sig = inspect.signature(func)
        if "debug" not in sig.parameters:
            raise TypeError(
                f"@lightweight_debuggable_component requires '{func.__name__}' to have "
                f"a 'debug' parameter (e.g. debug: bool = False)"
            )

        # Get source file info for logging
        try:
            source_file = inspect.getfile(func)
            source_path = Path(source_file).resolve()  # Get absolute path
            logger.debug(f"Processing component '{func.__name__}' from {source_path}")
        except (OSError, TypeError):
            source_file = "<unknown>"
            source_path = Path("<unknown>")
            logger.warning(
                f"Processing component '{func.__name__}' from unknown source"
            )

        # Determine debugger package to install (only if auto_install_packages is True)
        if auto_install_packages:
            debugger_package = debugger_type
            packages_to_install = list(component_kwargs.get("packages_to_install", []))

            # Always add loguru for better logging in components
            if "loguru" not in packages_to_install:
                packages_to_install.append("loguru")

            if debugger_package not in packages_to_install:
                packages_to_install.append(debugger_package)

            component_kwargs["packages_to_install"] = packages_to_install
            logger.debug(f"packages_to_install: {packages_to_install}")
        else:
            logger.debug(
                "Skipping automatic package installation (auto_install_packages=False)"
            )

        # Get the original function source code
        try:
            original_source = inspect.getsource(func)
            logger.debug(
                f"Extracted source code for {func.__name__} ({len(original_source)} chars)"
            )
        except OSError as e:
            logger.error(f"Cannot get source code for {func.__name__}: {e}")
            # Fallback to original function without debugging
            return component(**component_kwargs)(func)

        def inject_debugging_code(source_code: str) -> str:
            """Inject debugging code using AST parsing for robustness."""
            try:
                # Parse source into AST for robust function finding
                tree = ast.parse(source_code)

                # Find the target function definition
                target_func_node = None
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == func.__name__:
                        target_func_node = node
                        break

                if not target_func_node:
                    logger.warning(
                        f"Could not find function '{func.__name__}' in AST, using fallback"
                    )
                    return _inject_debugging_fallback(source_code)

                # Get line number and inject debugging code
                func_start_line = (
                    target_func_node.lineno - 1
                )  # AST uses 1-based line numbers
                lines = source_code.split("\n")

                # Find the line with ':' that ends the function signature
                # We need to find where the function signature actually ends
                colon_line = func_start_line
                paren_count = 0
                found_opening_paren = False

                while colon_line < len(lines):
                    line = lines[colon_line]
                    for char in line:
                        if char == "(":
                            paren_count += 1
                            found_opening_paren = True
                        elif char == ")":
                            paren_count -= 1
                        elif char == ":" and found_opening_paren and paren_count == 0:
                            # Found the colon that ends the function signature
                            break
                    else:
                        # If we didn't break out of the inner loop, continue to next line
                        colon_line += 1
                        continue
                    # If we broke out of the inner loop, we found our colon
                    break

                # Find first non-empty line after the colon (skip docstring if present)
                body_start = colon_line + 1
                while body_start < len(lines) and not lines[body_start].strip():
                    body_start += 1

                # If the first non-empty line is a docstring, skip it
                if body_start < len(lines) and lines[body_start].strip().startswith(
                    ('"""', "'''", 'r"""', "r'''")
                ):
                    # Find the end of the docstring - extract the actual triple-quote delimiter
                    stripped = lines[body_start].strip()
                    if stripped.startswith(('r"""', "r'''")):
                        quote_type = stripped[1:4]  # skip 'r', take '"""' or "'''"
                    else:
                        quote_type = stripped[:3]

                    # Check if docstring ends on the same line
                    if (
                        lines[body_start].strip().endswith(quote_type)
                        and len(lines[body_start].strip()) > 3
                    ):
                        body_start += 1
                    else:
                        # Multi-line docstring - find the end
                        body_start += 1
                        while body_start < len(lines) and not lines[
                            body_start
                        ].strip().endswith(quote_type):
                            body_start += 1
                        body_start += 1  # Move past the closing quotes

                    # Find next non-empty line after docstring
                    while body_start < len(lines) and not lines[body_start].strip():
                        body_start += 1

                if body_start >= len(lines):
                    logger.warning("Could not find function body, using fallback")
                    return _inject_debugging_fallback(source_code)

                # Get indentation
                first_body_line = lines[body_start]
                indent = len(first_body_line) - len(first_body_line.lstrip())
                indent_str = " " * indent

                # Generate debugging code based on debugger type
                debug_lines = _generate_debug_code(
                    debugger_type, debug_port, indent_str
                )

                # Insert debugging code
                modified_lines = lines[:body_start] + debug_lines + lines[body_start:]
                result = "\n".join(modified_lines)

                logger.debug(
                    f"Successfully injected {debugger_type} debugging code into {func.__name__}"
                )
                return result

            except Exception as e:
                logger.error(
                    f"AST parsing failed for {func.__name__}: {e}, using fallback"
                )
                return _inject_debugging_fallback(source_code)

        def _inject_debugging_fallback(source_code: str) -> str:
            """Fallback to string-based injection if AST fails."""
            lines = source_code.split("\n")

            # Find function definition line (more robust search)
            func_def_line = -1
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith(f"def {func.__name__}(") or stripped.startswith(
                    f"def {func.__name__} ("
                ):
                    func_def_line = i
                    break

            if func_def_line == -1:
                logger.error(f"Could not find function definition for {func.__name__}")
                return source_code

            # Find function body start
            body_start = func_def_line + 1
            while body_start < len(lines) and not lines[body_start].strip():
                body_start += 1

            if body_start >= len(lines):
                return source_code

            # Get indentation and inject
            first_body_line = lines[body_start]
            indent = len(first_body_line) - len(first_body_line.lstrip())
            indent_str = " " * indent

            debug_lines = _generate_debug_code(debugger_type, debug_port, indent_str)
            modified_lines = lines[:body_start] + debug_lines + lines[body_start:]

            logger.debug(f"Fallback injection successful for {func.__name__}")
            return "\n".join(modified_lines)

        def _generate_debug_code(debugger_type: str, port: int, indent: str) -> list:
            """Generate debugging code based on debugger type."""
            if debugger_type == "debugpy":
                return [
                    f"{indent}if debug:",
                    f"{indent}    import debugpy",
                    f'{indent}    debugpy.listen(("0.0.0.0", {port}))',
                    f"{indent}    debugpy.wait_for_client()",
                    f"{indent}    debugpy.breakpoint()",
                    f"{indent}",
                ]
            elif debugger_type == "remote-pdb":
                return [
                    f"{indent}if debug:",
                    f"{indent}    import remote_pdb",
                    f"{indent}    remote_pdb.RemotePdb('0.0.0.0', {port}).set_trace()",
                    f"{indent}",
                ]
            else:
                logger.error(f"Unsupported debugger type: {debugger_type}")
                return [f"{indent}# Unsupported debugger type: {debugger_type}"]

        # Monkey-patch inspect.getsource for this component
        original_getsource = inspect.getsource

        def patched_getsource(obj):
            if obj is func:
                modified_source = inject_debugging_code(original_source)
                logger.debug(f"Returning modified source for {func.__name__}")
                return modified_source
            return original_getsource(obj)

        # Apply monkey patch temporarily
        inspect.getsource = patched_getsource

        try:
            # Apply the KFP component decorator with all passed arguments
            component_func = component(**component_kwargs)(func)
            logger.debug(f"Successfully created debuggable component '{func.__name__}'")

        finally:
            # Always restore original inspect.getsource
            inspect.getsource = original_getsource

        return component_func

    return decorator
