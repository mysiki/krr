from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import typer
import urllib3
from pydantic import ValidationError  # noqa: F401

from robusta_krr import formatters as concrete_formatters  # noqa: F401
from robusta_krr.core.abstract import formatters
from robusta_krr.core.abstract.strategies import BaseStrategy
from robusta_krr.core.models.config import Config
from robusta_krr.core.runner import Runner
from robusta_krr.utils.version import get_version

app = typer.Typer(pretty_exceptions_show_locals=False, pretty_exceptions_short=True, no_args_is_help=True)

# NOTE: Disable insecure request warnings, as it might be expected to use self-signed certificates inside the cluster
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("krr")


@app.command(rich_help_panel="Utils")
def version() -> None:
    typer.echo(get_version())


def __process_type(_T: type) -> type:
    """Process type to a python literal"""
    if _T in (int, float, str, bool, datetime, UUID):
        return _T
    elif _T is Optional:
        return Optional[{__process_type(_T.__args__[0])}]  # type: ignore
    else:
        return str  # If the type is unknown, just use str and let pydantic handle it


def load_commands() -> None:
    for strategy_name, strategy_type in BaseStrategy.get_all().items():  # type: ignore
        # NOTE: This wrapper here is needed to avoid the strategy_name being overwritten in the loop
        def strategy_wrapper(_strategy_name: str = strategy_name):
            def run_strategy(
                ctx: typer.Context,
                kubeconfig: Optional[str] = typer.Option(
                    None,
                    "--kubeconfig",
                    "-k",
                    help="Path to kubeconfig file. If not provided, will attempt to find it.",
                    rich_help_panel="Kubernetes Settings",
                ),
                clusters: List[str] = typer.Option(
                    None,
                    "--context",
                    "--cluster",
                    "-c",
                    help="List of clusters to run on. By default, will run on the current cluster. Use --all-clusters to run on all clusters.",
                    rich_help_panel="Kubernetes Settings",
                ),
                all_clusters: bool = typer.Option(
                    False,
                    "--all-clusters",
                    help="Run on all clusters. Overrides --context.",
                    rich_help_panel="Kubernetes Settings",
                ),
                namespaces: List[str] = typer.Option(
                    None,
                    "--namespace",
                    "-n",
                    help="List of namespaces to run on. By default, will run on all namespaces except 'kube-system'.",
                    rich_help_panel="Kubernetes Settings",
                ),
                resources: List[str] = typer.Option(
                    None,
                    "--resource",
                    "-r",
                    help="List of resources to run on (Deployment, StatefulSet, DaemonSet, Job, Rollout). By default, will run on all resources. Case insensitive.",
                    rich_help_panel="Kubernetes Settings",
                ),
                selector: Optional[str] = typer.Option(
                    None,
                    "--selector",
                    "-s",
                    help="Selector (label query) to filter on, supports '=', '==', and '!='.(e.g. -s key1=value1,key2=value2). Matching objects must satisfy all of the specified label constraints.",
                    rich_help_panel="Kubernetes Settings",
                ),
                prometheus_url: Optional[str] = typer.Option(
                    None,
                    "--prometheus-url",
                    "-p",
                    help="Prometheus URL. If not provided, will attempt to find it in kubernetes cluster",
                    rich_help_panel="Prometheus Settings",
                ),
                prometheus_auth_header: Optional[str] = typer.Option(
                    None,
                    "--prometheus-auth-header",
                    help="Prometheus authentication header.",
                    rich_help_panel="Prometheus Settings",
                ),
                prometheus_other_headers: Optional[List[str]] = typer.Option(
                    None,
                    "--prometheus-headers",
                    "-H",
                    help="Additional headers to add to Prometheus requests. Format as 'key: value', for example 'X-MyHeader: 123'. Trailing whitespaces will be stripped.",
                    rich_help_panel="Prometheus Settings",
                ),
                prometheus_ssl_enabled: bool = typer.Option(
                    False,
                    "--prometheus-ssl-enabled",
                    help="Enable SSL for Prometheus requests.",
                    rich_help_panel="Prometheus Settings",
                ),
                prometheus_cluster_label: Optional[str] = typer.Option(
                    None,
                    "--prometheus-cluster-label",
                    "-l",
                    help="The label in prometheus for your cluster.(Only relevant for centralized prometheus)",
                    rich_help_panel="Prometheus Settings",
                ),
                prometheus_label: str = typer.Option(
                    None,
                    "--prometheus-label",
                    help="The label in prometheus used to differentiate clusters. (Only relevant for centralized prometheus)",
                    rich_help_panel="Prometheus Settings",
                ),
                eks_managed_prom: bool = typer.Option(
                    False,
                    "--eks-managed-prom",
                    help="Adds additional signitures for eks prometheus connection.",
                    rich_help_panel="Prometheus EKS Settings",
                ),
                eks_managed_prom_profile_name: Optional[str] = typer.Option(
                    None,
                    "--eks-profile-name",
                    help="Sets the profile name for eks prometheus connection.",
                    rich_help_panel="Prometheus EKS Settings",
                ),
                eks_access_key: Optional[str] = typer.Option(
                    None,
                    "--eks-access-key",
                    help="Sets the access key for eks prometheus connection.",
                    rich_help_panel="Prometheus EKS Settings",
                ),
                eks_secret_key: Optional[str] = typer.Option(
                    None,
                    "--eks-secret-key",
                    help="Sets the secret key for eks prometheus connection.",
                    rich_help_panel="Prometheus EKS Settings",
                ),
                eks_service_name: Optional[str] = typer.Option(
                    "aps",
                    "--eks-service-name",
                    help="Sets the service name for eks prometheus connection.",
                    rich_help_panel="Prometheus EKS Settings",
                ),
                eks_managed_prom_region: Optional[str] = typer.Option(
                    None,
                    "--eks-managed-prom-region",
                    help="Sets the region for eks prometheus connection.",
                    rich_help_panel="Prometheus EKS Settings",
                ),
                coralogix_token: Optional[str] = typer.Option(
                    None,
                    "--coralogix-token",
                    help="Adds the token needed to query Coralogix managed prometheus.",
                    rich_help_panel="Prometheus Coralogix Settings",
                ),
                openshift: bool = typer.Option(
                    False,
                    "--openshift",
                    help="Used when running by Robusta inside an OpenShift cluster.",
                    rich_help_panel="Prometheus Openshift Settings",
                    hidden=True,
                ),
                cpu_min_value: int = typer.Option(
                    10,
                    "--cpu-min",
                    help="Sets the minimum recommended cpu value in millicores.",
                    rich_help_panel="Recommendation Settings",
                ),
                memory_min_value: int = typer.Option(
                    100,
                    "--mem-min",
                    help="Sets the minimum recommended memory value in MB.",
                    rich_help_panel="Recommendation Settings",
                ),
                max_workers: int = typer.Option(
                    10,
                    "--max-workers",
                    "-w",
                    help="Max workers to use for async requests.",
                    rich_help_panel="Threading Settings",
                ),
                format: str = typer.Option(
                    "table",
                    "--formatter",
                    "-f",
                    help=f"Output formatter ({', '.join(formatters.list_available())})",
                    rich_help_panel="Logging Settings",
                ),
                show_cluster_name: bool = typer.Option(
                    False, "--show-cluster-name", help="In table output, always show the cluster name even for a single cluster", rich_help_panel="Output Settings"
                ),
                verbose: bool = typer.Option(
                    False, "--verbose", "-v", help="Enable verbose mode", rich_help_panel="Logging Settings"
                ),
                quiet: bool = typer.Option(
                    False, "--quiet", "-q", help="Enable quiet mode", rich_help_panel="Logging Settings"
                ),
                log_to_stderr: bool = typer.Option(
                    False, "--logtostderr", help="Pass logs to stderr", rich_help_panel="Logging Settings"
                ),
                width: Optional[int] = typer.Option(
                    None,
                    "--width",
                    help="Width of the output. Will use console width by default.",
                    rich_help_panel="Logging Settings",
                ),
                file_output: Optional[str] = typer.Option(
                    None, "--fileoutput", help="Print the output to a file", rich_help_panel="Output Settings"
                ),
                slack_output: Optional[str] = typer.Option(
                    None,
                    "--slackoutput",
                    help="Send to output to a slack channel, must have SLACK_BOT_TOKEN",
                    rich_help_panel="Output Settings",
                ),
                **strategy_args,
            ) -> None:
                f"""Run KRR using the `{_strategy_name}` strategy"""

                try:
                    config = Config(
                        kubeconfig=kubeconfig,
                        clusters="*" if all_clusters else clusters,
                        namespaces="*" if "*" in namespaces else namespaces,
                        resources="*" if "*" in resources else resources,
                        selector=selector,
                        prometheus_url=prometheus_url,
                        prometheus_auth_header=prometheus_auth_header,
                        prometheus_other_headers=prometheus_other_headers,
                        prometheus_ssl_enabled=prometheus_ssl_enabled,
                        prometheus_cluster_label=prometheus_cluster_label,
                        prometheus_label=prometheus_label,
                        eks_managed_prom=eks_managed_prom,
                        eks_managed_prom_region=eks_managed_prom_region,
                        eks_managed_prom_profile_name=eks_managed_prom_profile_name,
                        eks_access_key=eks_access_key,
                        eks_secret_key=eks_secret_key,
                        eks_service_name=eks_service_name,
                        coralogix_token=coralogix_token,
                        openshift=openshift,
                        max_workers=max_workers,
                        format=format,
                        show_cluster_name=show_cluster_name,
                        verbose=verbose,
                        cpu_min_value=cpu_min_value,
                        memory_min_value=memory_min_value,
                        quiet=quiet,
                        log_to_stderr=log_to_stderr,
                        width=width,
                        file_output=file_output,
                        slack_output=slack_output,
                        strategy=_strategy_name,
                        other_args=strategy_args,
                    )
                    Config.set_config(config)
                except ValidationError:
                    logger.exception("Error occured while parsing arguments")
                else:
                    runner = Runner()
                    asyncio.run(runner.run())

            run_strategy.__name__ = strategy_name
            signature = inspect.signature(run_strategy)
            run_strategy.__signature__ = signature.replace(  # type: ignore
                parameters=list(signature.parameters.values())[:-1]
                + [
                    inspect.Parameter(
                        name=field_name,
                        kind=inspect.Parameter.KEYWORD_ONLY,
                        default=typer.Option(
                            field_meta.default,
                            f"--{field_name}",
                            help=f"{field_meta.field_info.description}",
                            rich_help_panel="Strategy Settings",
                        ),
                        annotation=__process_type(field_meta.type_),
                    )
                    for field_name, field_meta in strategy_type.get_settings_type().__fields__.items()
                ]
            )

            app.command(rich_help_panel="Strategies")(run_strategy)

        strategy_wrapper()


def run() -> None:
    load_commands()
    app()


if __name__ == "__main__":
    run()
