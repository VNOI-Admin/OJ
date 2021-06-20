import csv
import io


def parse_csv_ranking(raw):
    reader = csv.DictReader(io.StringIO(raw))

    show_team = 'Team' in reader.fieldnames
    problems = [reader.fieldnames[i] for i in range(3 if show_team else 2, len(reader.fieldnames) - 2, 2)]
    users = []

    for row in reader:
        users.append({
            'username': row['Username'],
            'full_name': row['User'],
            'scores': [float(row[prob]) for prob in problems],
            'total_score': float(row['Global']),
        })

    users.sort(key=lambda p: p['total_score'], reverse=True)

    return users, problems
