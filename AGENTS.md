# Agent Operating Notes

This project contains operational knowledge for delivery-route review and admin workflow assistance.

## Schedule booking workflow

When the user asks to arrange, modify, publish, delete, or verify next-week delivery-driver schedules in the Fantuan admin backend, read and follow:

- `docs/schedule_booking_workflow.md`

The schedule workflow document records the learned rules for:

- Opening `配送管理 -> 班表 -> 整理与发布 -> 下周班表`.
- Selecting New York and then either Flushing or Brooklyn according to the user's label.
- Extracting driver IDs from DingTalk screenshots.
- Interpreting ambiguous time ranges.
- Adding drivers to existing schedule cells.
- Creating missing time slots only after checking each required day.
- Deleting a driver from an existing shift.
- Saving and publishing after each driver's schedule.
- Stopping immediately if the save response is anything other than `已保存`.

Treat this file as required context before operating the admin schedule UI.
