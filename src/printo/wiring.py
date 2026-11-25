"""Put the pieces together. Nothing in here decides what a job means."""

from dataclasses import dataclass

from printo.clock import Clock, SystemClock
from printo.config import Settings
from printo.convert.office import Office
from printo.convert.worker import Converter
from printo.printing.cups import Cups, PrinterPort
from printo.printing.watch import PrintWatch
from printo.services.citizenship import Citizenship
from printo.services.events import Events
from printo.services.ingest import Ingest
from printo.services.limits import Limits
from printo.services.printing import PrintService
from printo.services.trash import Trash
from printo.storage.database import Database
from printo.storage.files import Files
from printo.storage.jobs import JobStore


@dataclass
class Context:
    settings: Settings
    clock: Clock
    db: Database
    jobs: JobStore
    files: Files
    events: Events
    cups: PrinterPort
    office: Office
    converter: Converter
    watch: PrintWatch
    printing: PrintService
    trash: Trash
    ingest: Ingest
    citizenship: Citizenship
    limits: Limits


def build_context(settings: Settings, cups: PrinterPort | None = None, clock: Clock | None = None) -> Context:
    clock = clock or SystemClock()
    db = Database(settings.data_dir / "printo.db")
    files = Files(settings.data_dir)
    files.ensure()
    jobs = JobStore(db, clock)
    events = Events(settings.sse_heartbeat_seconds)
    office = Office(settings.soffice_bin, settings.office_timeout_seconds)
    converter = Converter(settings, jobs, files, events, office)
    printer = cups or Cups(settings.printer)
    watch = PrintWatch(settings, jobs, printer, events)
    limits = Limits(settings, files)
    return Context(
        settings=settings, clock=clock, db=db, jobs=jobs, files=files, events=events, cups=printer, office=office,
        converter=converter, watch=watch, limits=limits,
        printing=PrintService(settings, jobs, files, printer, events, watch),
        trash=Trash(jobs, files, printer, events, converter),
        ingest=Ingest(settings, jobs, files, limits, converter, events),
        citizenship=Citizenship(jobs, files, events),
    )
