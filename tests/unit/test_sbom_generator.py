import os
import tempfile

import pytest

from strategy_sandbox.security.sbom_generator import SBOMGenerator


class DummyComponent:
    def __init__(self, name, version, component_license=None, purl=None):
        self.name = name
        self.version = version
        self.license = component_license
        self.purl = purl


class DummyVulnerability:
    def __init__(self, vuln_id, description, affected_components):
        self.id = vuln_id
        self.description = description
        self.affected_components = affected_components


class DummyAnalyzer:
    def analyze(self, source_path):
        return [
            DummyComponent("foo", "1.0.0", "MIT"),
            DummyComponent("bar", "2.1.3", "Apache-2.0"),
        ]


class DummyVulnCollector:
    def collect(self, components):
        return [DummyVulnerability("CVE-1234-5678", "Test vuln", [components[0]])]


@pytest.fixture
def sbom_generator():
    return SBOMGenerator(analyzer=DummyAnalyzer(), vuln_collector=DummyVulnCollector())


def test_generate_cyclonedx_json(sbom_generator):
    sbom = sbom_generator.generate_sbom(source_path=".", output_format="cyclonedx-json")
    assert "foo" in sbom
    assert "bar" in sbom
    assert "MIT" in sbom or "NOASSERTION" in sbom


def test_generate_cyclonedx_xml(sbom_generator):
    sbom = sbom_generator.generate_sbom(source_path=".", output_format="cyclonedx-xml")
    assert "<bom" in sbom
    assert "foo" in sbom


def test_generate_spdx_json(sbom_generator):
    sbom = sbom_generator.generate_sbom(source_path=".", output_format="spdx-json")
    assert "foo" in sbom
    assert "bar" in sbom
    assert "MIT" in sbom or "NOASSERTION" in sbom


def test_generate_spdx_yaml(sbom_generator):
    sbom = sbom_generator.generate_sbom(source_path=".", output_format="spdx-yaml")
    assert "foo" in sbom
    assert "bar" in sbom


def test_sbom_file_output(sbom_generator):
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        sbom_generator.generate_sbom(source_path=".", output_format="cyclonedx-json", output_file=tmp.name)
        tmp.close()
        with open(tmp.name, "r") as f:
            content = f.read()
            assert "foo" in content
        os.unlink(tmp.name)


def test_cli_argument_addition():
    import argparse

    parser = argparse.ArgumentParser()
    SBOMGenerator.add_cli_arguments(parser)
    args = parser.parse_args([])
    assert hasattr(args, "sbom_format")
    assert hasattr(args, "sbom_output")


def test_run_from_cli(sbom_generator):
    class Args:
        source = "."
        sbom_format = "cyclonedx-json"
        sbom_output = None

    result = sbom_generator.run_from_cli(Args())
    assert "foo" in result
