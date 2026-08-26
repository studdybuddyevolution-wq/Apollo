"""Citation & Fact-Checking System - Verify Answers Against Sources

Automatically extracts citations, cross-references claims against indexed sources,
and provides confidence scores for responses.
"""

from typing import List, Dict, Tuple, Any
import re
import streamlit as st
from dataclasses import dataclass


@dataclass
class Citation:
    """A single citation/reference."""
    source_id: str
    source_name: str
    source_type: str  # 'file', 'web', 'memory'
    page: int = None
    confidence: float = 1.0  # 0-1 confidence score
    quote: str = ""  # Relevant quote from source


class CitationExtractor:
    """Extract and validate citations from LLM responses."""
    
    def __init__(self, indexed_sources: List[Dict]):
        """Initialize extractor.
        
        Args:
            indexed_sources: List of {name, kind, ...} dicts from session state
        """
        self.indexed_sources = indexed_sources
    
    def extract_citations_from_response(self, response: str) -> Tuple[str, List[Citation]]:
        """Extract citation markers from LLM response.
        
        Args:
            response: LLM response text
        
        Returns:
            Tuple of (cleaned_response, list of Citation objects)
        """
        citations = []
        
        # Pattern 1: [source: S1], [source: p.5], etc.
        pattern1 = r'\[source:?\s*([^\]]+)\]'
        matches1 = re.finditer(pattern1, response)
        
        for match in matches1:
            citation_ref = match.group(1).strip()
            citation = self._parse_citation_reference(citation_ref)
            if citation:
                citations.append(citation)
        
        # Pattern 2: (Source: filename) or (from X)
        pattern2 = r'\((?:source|from|src):?\s*([^)]+)\)'
        matches2 = re.finditer(pattern2, response)
        
        for match in matches2:
            citation_ref = match.group(1).strip()
            citation = self._parse_citation_reference(citation_ref)
            if citation:
                citations.append(citation)
        
        # Remove citation markers from display text
        cleaned = re.sub(pattern1, '', response)
        cleaned = re.sub(pattern2, '', cleaned)
        
        return cleaned, citations
    
    def _parse_citation_reference(self, ref: str) -> Citation:
        """Parse citation reference string into Citation object.
        
        Args:
            ref: Reference string like "S1" or "p.5" or "filename.pdf"
        
        Returns:
            Citation object or None
        """
        ref = ref.strip()
        
        # S1, S2, etc.
        if ref.startswith('S') and ref[1:].isdigit():
            source_id = ref
            return Citation(source_id=source_id, source_name=f"Source {ref}", source_type="indexed")
        
        # p.5, p.123
        if ref.startswith('p.'):
            try:
                page = int(ref[2:])
                return Citation(source_id=f"p{page}", source_name=f"Page {page}", source_type="page", page=page)
            except ValueError:
                pass
        
        # Match against indexed sources
        for source in self.indexed_sources:
            if ref.lower() in source.get("name", "").lower():
                return Citation(
                    source_id=source.get("name"),
                    source_name=source.get("name"),
                    source_type=source.get("kind", "file")
                )
        
        # Default
        return Citation(source_id=ref, source_name=ref, source_type="unknown")


class FactChecker:
    """Fact-check claims against available sources."""
    
    def __init__(self, llm_generator, vector_db=None):
        """Initialize fact checker.
        
        Args:
            llm_generator: Function to call LLM
            vector_db: FAISS vector database for semantic search
        """
        self.llm_generator = llm_generator
        self.vector_db = vector_db
    
    def extract_claims(self, text: str) -> List[str]:
        """Extract factual claims from text.
        
        Args:
            text: Response text
        
        Returns:
            List of extracted claims
        """
        claim_prompt = f"""Extract the main factual claims (not opinions) from this text as a numbered list.
Keep each claim to 1-2 sentences.

Text: {text}

Claims:"""
        
        response = self.llm_generator([{"role": "user", "content": claim_prompt}])
        
        # Parse numbered list
        claims = []
        for line in response.split('\n'):
            line = line.strip()
            if line and line[0].isdigit():
                claim = line.lstrip('0123456789.)) ').strip()
                if claim:
                    claims.append(claim)
        
        return claims
    
    def check_claim(self, claim: str, context: str = "") -> Dict[str, Any]:
        """Check a single claim against sources.
        
        Args:
            claim: Factual claim to verify
            context: Relevant source context
        
        Returns:
            Dict with verdict, confidence, explanation
        """
        if not context:
            return {
                "claim": claim,
                "verdict": "UNVERIFIED",
                "confidence": 0.0,
                "explanation": "No relevant sources found."
            }
        
        check_prompt = f"""Given this claim and source material, determine if the claim is:
- SUPPORTED: Clearly stated in or directly implied by the sources
- CONTRADICTED: Directly contradicts the sources
- UNVERIFIED: Not mentioned in sources but not contradicted
- PARTIALLY_CORRECT: Partially true but with important nuances

Claim: {claim}

Source Material:
{context}

Respond in JSON: {{"verdict": "...", "confidence": 0.0-1.0, "explanation": "..."}}"""
        
        response = self.llm_generator([{"role": "user", "content": check_prompt}])
        
        # Parse JSON response
        import json
        try:
            result = json.loads(response)
            result["claim"] = claim
            return result
        except json.JSONDecodeError:
            return {
                "claim": claim,
                "verdict": "UNVERIFIED",
                "confidence": 0.5,
                "explanation": response[:200]
            }
    
    def verify_response(self, response: str, context: str = "") -> Dict[str, Any]:
        """Fact-check an entire response.
        
        Args:
            response: LLM response text
            context: Available source context
        
        Returns:
            Dict with overall verdict and per-claim results
        """
        claims = self.extract_claims(response)
        
        checked_claims = []
        for claim in claims:
            result = self.check_claim(claim, context)
            checked_claims.append(result)
        
        # Calculate overall confidence
        if checked_claims:
            supported = sum(1 for c in checked_claims if c["verdict"] == "SUPPORTED")
            overall_confidence = supported / len(checked_claims)
        else:
            overall_confidence = 0.5
        
        return {
            "overall_confidence": overall_confidence,
            "verified_claims": checked_claims,
            "needs_review": overall_confidence < 0.7
        }


def render_citations(citations: List[Citation]):
    """Render citations in Streamlit.
    
    Args:
        citations: List of Citation objects
    """
    if not citations:
        return
    
    with st.expander(f"📎 Sources Used ({len(citations)})", expanded=True):
        for i, citation in enumerate(citations, 1):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{citation.source_id}** — {citation.source_name}")
                if citation.page:
                    st.caption(f"Page {citation.page}")
                if citation.quote:
                    st.markdown(f"> {citation.quote}")
            with col2:
                st.metric("Confidence", f"{citation.confidence:.0%}")


def render_fact_check(verification: Dict[str, Any]):
    """Render fact-check results in Streamlit.
    
    Args:
        verification: Output from FactChecker.verify_response
    """
    confidence = verification["overall_confidence"]
    
    if confidence >= 0.8:
        st.success(f"✅ High confidence ({confidence:.0%}) - Claims well-supported by sources")
    elif confidence >= 0.5:
        st.warning(f"⚠️ Medium confidence ({confidence:.0%}) - Some claims unverified")
    else:
        st.error(f"❌ Low confidence ({confidence:.0%}) - Limited source support")
    
    with st.expander("View claim verification", expanded=False):
        for claim_result in verification["verified_claims"]:
            verdict = claim_result["verdict"]
            conf = claim_result["confidence"]
            
            emoji_map = {
                "SUPPORTED": "✅",
                "CONTRADICTED": "❌",
                "UNVERIFIED": "❓",
                "PARTIALLY_CORRECT": "⚠️"
            }
            
            st.markdown(f"{emoji_map.get(verdict, '•')} **{verdict}** ({conf:.0%})")
            st.caption(f"Claim: {claim_result['claim']}")
            st.caption(f"Explanation: {claim_result['explanation']}")
