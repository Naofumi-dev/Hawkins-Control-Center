"""Hosted personal OnlineJobs adapter, adapted from the existing Hawkins form flow.

No legacy Sheet/Telegram queue is loaded. A private, isolated browser profile and
reviewed account-page identity selector must be configured before use.
"""
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

from .acquisition import normalize_job
from .gmail import OWNER_EMAIL
from .providers import ProviderConfigurationError, ProviderError


class PersonalOnlineJobs:
    def __init__(self):
        profile=os.environ.get("HAWKINS_ONLINEJOBS_PROFILE","")
        self.identity_url=os.environ.get("HAWKINS_ONLINEJOBS_ACCOUNT_URL","")
        self.identity_selector=os.environ.get("HAWKINS_ONLINEJOBS_EMAIL_SELECTOR","")
        u=urlsplit(self.identity_url)
        if not profile or not Path(profile).is_absolute() or not self.identity_selector or u.scheme!="https" or u.hostname not in ("www.onlinejobs.ph","onlinejobs.ph") or "/job/" in u.path or u.username:
            raise ProviderConfigurationError("Personal OnlineJobs worker needs reviewed account selectors and an isolated session")
        path=Path(profile)
        if not path.is_dir() or path.is_symlink() or path.stat().st_uid!=os.getuid() or stat.S_IMODE(path.stat().st_mode)&0o077:
            raise ProviderConfigurationError("Private OnlineJobs session directory required")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ProviderConfigurationError("Install the pinned hosted browser worker dependencies") from None
        self.engine=sync_playwright().start()
        self.context=self.engine.chromium.launch_persistent_context(str(path),headless=True)
        self.page=self.context.new_page()
        self.verified=False

    def verify(self):
        self.verified=False
        self.page.goto(self.identity_url,wait_until="domcontentloaded")
        if self.page.url!=self.identity_url:
            raise ProviderConfigurationError("OnlineJobs session expired or account page changed")
        field=self.page.locator(self.identity_selector)
        if field.count()!=1:
            raise ProviderConfigurationError("Personal identity could not be verified")
        email=field.input_value() if field.evaluate("el => ['INPUT','TEXTAREA'].includes(el.tagName)") else field.inner_text()
        if email.strip().lower()!=OWNER_EMAIL:
            raise ProviderConfigurationError("Wrong OnlineJobs account")
        self.verified=True

    def inspect(self,url):
        if not self.verified:
            raise ProviderConfigurationError("Verify platform owner first")
        # Validate references again at the delivery boundary.
        job=normalize_job({"source_url":url,"title":"Inspection","description":"Owner-approved application"})
        if job["platform"]!="onlinejobs":
            raise ValueError("Unsupported platform")
        self.page.goto(job["source_url"],wait_until="domcontentloaded")
        if "/login" in self.page.url:
            raise ProviderConfigurationError("OnlineJobs session expired")
        actual=normalize_job({"source_url":self.page.url,"title":"Inspection","description":"Verified destination"})
        if actual["job_key"]!=job["job_key"] or actual["platform"]!="onlinejobs":
            raise ProviderError("Job destination changed")
        # The applied state must come from the platform's application controls,
        # never a phrase in the employer-authored job description.
        selector=os.environ.get("HAWKINS_ONLINEJOBS_APPLIED_SELECTOR","")
        if not selector:
            raise ProviderConfigurationError("Review the platform confirmation selector before enabling submissions")
        applied=self.page.locator(selector)
        if applied.count()==1:
            proof=applied.inner_text()
            if re.search(r"Date Applied:\s*\d{4}-\d{2}-\d{2}",proof):
                return {"status":"applied","reference":job["source_url"]+"#application-record"}
        button=self.page.get_by_role("button",name="APPLY FOR THIS JOB",exact=True)
        return {"status":"open" if button.count()==1 and button.is_enabled() else "closed_or_unknown"}

    def prepare(self,attempt):
        self.page.get_by_role("button",name="APPLY FOR THIS JOB",exact=True).click()
        self.page.wait_for_url("**/apply",timeout=15000)
        destination=self.page.url.removesuffix("/apply")
        actual=normalize_job({"source_url":destination,"title":"Inspection","description":"Verified form destination"})
        if actual["platform"]!="onlinejobs" or actual["job_key"]!=attempt["application_payload"]["job_key"]:
            raise ProviderError("Unexpected platform destination")
        self.page.locator("#subject").fill(attempt["subject"])
        self.page.locator("#message").fill(attempt["body"])
        points=self.page.locator("input[name='points']")
        if points.count()!=1:
            raise ProviderError("Application point control changed")
        points.fill(str(attempt["application_payload"]["apply_points"]))
        if self.page.locator("#subject").input_value()!=attempt["subject"] or self.page.locator("#message").input_value()!=attempt["body"] or points.input_value()!="1":
            raise ProviderError("Form differs from the approved revision")

    def submit(self):
        self.page.get_by_role("button",name="SEND EMAIL",exact=True).click()
        self.page.wait_for_load_state("domcontentloaded")

    def close(self):
        try:
            self.context.close()
        finally:
            self.engine.stop()
