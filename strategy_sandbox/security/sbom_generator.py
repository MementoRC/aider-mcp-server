import datetime
import logging
from typing import Dict, Optional

try:
    from cyclonedx.model.bom import Bom
    from cyclonedx.model.component import Component, ComponentType
    from cyclonedx.model.license import License as CycloneLicense
    from cyclonedx.model.vulnerability import BomTarget, Vulnerability
    from cyclonedx.output import OutputFormat as CycloneDXOutputFormat
    from cyclonedx.output import get_instance as get_cdx_writer
except ImportError:
    Bom = None  # type: ignore
    Component = None  # type: ignore
    Vulnerability = None  # type: ignore
    CycloneLicense = None  # type: ignore
    get_cdx_writer = None  # type: ignore
    CycloneDXOutputFormat = None  # type: ignore

try:
    import spdx.creationinfo
    import spdx.document
    import spdx.file
    import spdx.package
    import spdx.version
    import spdx.writers.json
    import spdx.writers.yaml
except ImportError:
    spdx = None

# Placeholder imports for integration
try:
    from .analyzer import DependencyAnalyzer
    from .collector import VulnerabilityCollector
    from .models import SBOMComponent, SBOMMetadata, SBOMVulnerability
except ImportError:
    # Fallbacks for code completion, real code should import actual modules
    DependencyAnalyzer = object
    VulnerabilityCollector = object
    SBOMComponent = object
    SBOMVulnerability = object
    SBOMMetadata = object

logger = logging.getLogger("sbom_generator")


class SBOMGenerator:
    """
    Generates Software Bill of Materials (SBOM) in CycloneDX 1.4 and SPDX 2.3 formats,
    with vulnerability and license correlation.
    """

    SUPPORTED_FORMATS = {
        "cyclonedx-json": "cyclonedx-json",
        "cyclonedx-xml": "cyclonedx-xml",
        "spdx-json": "spdx-json",
        "spdx-yaml": "spdx-yaml",
    }

    def __init__(
        self, analyzer: Optional[DependencyAnalyzer] = None, vuln_collector: Optional[VulnerabilityCollector] = None
    ):
        self.analyzer = analyzer or DependencyAnalyzer()
        self.vuln_collector = vuln_collector or VulnerabilityCollector()

    def generate_sbom(
        self,
        source_path: str,
        output_format: str = "cyclonedx-json",
        output_file: Optional[str] = None,
        ci_metadata: Optional[Dict] = None,
    ) -> str:
        """
        Generate an SBOM for the given source path.

        Args:
            source_path: Path to the project root.
            output_format: One of SUPPORTED_FORMATS.
            output_file: If provided, write SBOM to this file.
            ci_metadata: Optional build/provenance metadata.

        Returns:
            The SBOM as a string (JSON, XML, or YAML).
        """
        logger.info(f"Starting SBOM generation for {source_path} in format {output_format}")

        # 1. Analyze dependencies
        try:
            components = self.analyzer.analyze(source_path)
        except Exception as e:
            logger.error(f"Dependency analysis failed: {e}")
            raise

        # 2. Collect vulnerabilities
        try:
            vulnerabilities = self.vuln_collector.collect(components)
        except Exception as e:
            logger.error(f"Vulnerability collection failed: {e}")
            vulnerabilities = []

        # 3. Gather license and compliance info
        for comp in components:
            if not hasattr(comp, "license") or not comp.license:
                comp.license = self._detect_license(comp)

        # 4. Build metadata
        metadata = self._build_metadata(ci_metadata)

        # 5. Generate SBOM in requested format
        if output_format.startswith("cyclonedx"):
            sbom_str = self._generate_cyclonedx_sbom(components, vulnerabilities, metadata, output_format)
        elif output_format.startswith("spdx"):
            sbom_str = self._generate_spdx_sbom(components, vulnerabilities, metadata, output_format)
        else:
            logger.error(f"Unsupported SBOM format: {output_format}")
            raise ValueError(f"Unsupported SBOM format: {output_format}")

        # 6. Write to file if requested
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(sbom_str)
            logger.info(f"SBOM written to {output_file}")

        return sbom_str

    def _detect_license(self, component) -> str:
        # Placeholder: real implementation should use license detection tools
        logger.debug(f"Detecting license for {component.name}")
        return "NOASSERTION"

    def _build_metadata(self, ci_metadata: Optional[Dict]) -> Dict:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        metadata = {
            "timestamp": now,
            "tool": "SBOMGenerator",
            "version": "1.0.0",
        }
        if ci_metadata:
            metadata.update(ci_metadata)
        return metadata

    def _generate_cyclonedx_sbom(self, components, vulnerabilities, metadata, output_format) -> str:
        if Bom is None:
            logger.error("CycloneDX libraries not installed")
            raise ImportError("CycloneDX libraries not installed")

        bom = Bom()
        # Add components
        for comp in components:
            cdx_comp = Component(
                name=comp.name,
                version=comp.version,
                type=ComponentType.APPLICATION,
                purl=getattr(comp, "purl", None),
                licenses=[CycloneLicense(license_id=comp.license)] if comp.license else [],
                external_references=[],
            )
            bom.components.add(cdx_comp)

        # Add vulnerabilities
        for vuln in vulnerabilities:
            affected = [BomTarget(ref=comp.name) for comp in vuln.affected_components]
            cdx_vuln = Vulnerability(
                id=vuln.id,
                source=None,
                ratings=[],
                description=vuln.description,
                recommendations=[],
                advisories=[],
                analysis=None,
                affects=affected,
            )
            bom.vulnerabilities.add(cdx_vuln)

        # Add metadata
        bom.metadata.tools.add("SBOMGenerator")
        bom.metadata.timestamp = metadata.get("timestamp")

        # Output
        if output_format == "cyclonedx-json":
            writer = get_cdx_writer(bom, CycloneDXOutputFormat.JSON)
            return writer.output_as_string()
        elif output_format == "cyclonedx-xml":
            writer = get_cdx_writer(bom, CycloneDXOutputFormat.XML)
            return writer.output_as_string()
        else:
            logger.error(f"Unsupported CycloneDX output format: {output_format}")
            raise ValueError(f"Unsupported CycloneDX output format: {output_format}")

    def _generate_spdx_sbom(self, components, vulnerabilities, metadata, output_format) -> str:
        if spdx is None:
            logger.error("SPDX libraries not installed")
            raise ImportError("SPDX libraries not installed")

        doc = spdx.document.Document()
        doc.version = spdx.version.Version(2, 3)
        doc.creation_info = spdx.creationinfo.CreationInfo()
        doc.creation_info.created = metadata.get("timestamp")
        doc.creation_info.creators.append("Tool: SBOMGenerator/1.0.0")

        # Add packages
        for comp in components:
            pkg = spdx.package.Package(
                name=comp.name,
                downloadLocation="NOASSERTION",
                version=comp.version or "NOASSERTION",
            )
            pkg.licenseDeclared = comp.license or "NOASSERTION"
            doc.add_package(pkg)

        # Add vulnerabilities as annotations
        for vuln in vulnerabilities:
            for comp in vuln.affected_components:
                doc.add_annotation(
                    spdx.document.Annotation(
                        annotator="Tool: SBOMGenerator",
                        annotationDate=metadata.get("timestamp"),
                        annotationType="OTHER",
                        subject=comp.name,
                        comment=f"Vulnerability: {vuln.id} - {vuln.description}",
                    )
                )

        # Output
        if output_format == "spdx-json":
            return spdx.writers.json.write_document_to_string(doc)
        elif output_format == "spdx-yaml":
            return spdx.writers.yaml.write_document_to_string(doc)
        else:
            logger.error(f"Unsupported SPDX output format: {output_format}")
            raise ValueError(f"Unsupported SPDX output format: {output_format}")

    @classmethod
    def add_cli_arguments(cls, parser):
        """
        Add SBOM generation arguments to an argparse parser.
        """
        parser.add_argument(
            "--sbom-format",
            choices=list(cls.SUPPORTED_FORMATS.keys()),
            default="cyclonedx-json",
            help="SBOM output format",
        )
        parser.add_argument(
            "--sbom-output",
            type=str,
            help="Path to write SBOM artifact",
        )

    @classmethod
    def from_cli_args(cls, args):
        """
        Instantiate SBOMGenerator from CLI args.
        """
        return cls()

    def run_from_cli(self, args):
        """
        Run SBOM generation from CLI arguments.
        """
        return self.generate_sbom(
            source_path=args.source,
            output_format=args.sbom_format,
            output_file=args.sbom_output,
        )
