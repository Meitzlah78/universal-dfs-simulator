# shared NFL 2PT normalization helper

def historical_two_point_conversions(row):
    total=0.0
    for column in ('passing_2pt_conversions','rushing_2pt_conversions','receiving_2pt_conversions'):
        try:
            total+=float(row.get(column,0) or 0)
        except (TypeError,ValueError):
            pass
    return total
