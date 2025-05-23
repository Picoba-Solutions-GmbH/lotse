class PodResourceParser:
    @staticmethod
    def parse_memory(resource_str: str) -> str:
        units = {'': 1, 'Ki': 1024, 'Mi': 1024**2, 'Gi': 1024**3, 'Ti': 1024**4, 'Pi': 1024**5}

        unit = ''
        for suffix in ['Ki', 'Mi', 'Gi', 'Ti', 'Pi']:
            if resource_str.endswith(suffix):
                unit = suffix
                value = float(resource_str[:-len(suffix)])
                break
        else:
            value = float(resource_str)

        bytes_value = value * units.get(unit, 1)
        if bytes_value < 1024**2:
            return f"{int(bytes_value / 1024)} KB"
        elif bytes_value < 1024**3:
            return f"{int(bytes_value / 1024**2)} MB"
        elif bytes_value < 1024**4:
            return f"{(bytes_value / 1024**3):.2f} GB"
        elif bytes_value < 1024**5:
            return f"{(bytes_value / 1024**4):.2f} TB"
        else:
            return f"{(bytes_value / 1024**5):.2f} PB"

    @staticmethod
    def parse_cpu(resource_str: str) -> str:
        if resource_str.endswith('n'):
            return f"{float(f'{float(resource_str[:-1]) / 1e9:.3f}'.rstrip('0').rstrip('.'))} cores"
        elif resource_str.endswith('u'):
            return f"{float(f'{float(resource_str[:-1]) / 1e6:.3f}'.rstrip('0').rstrip('.'))} cores"
        elif resource_str.endswith('m'):
            return f"{float(f'{float(resource_str[:-1]):.3f}'.rstrip('0').rstrip('.'))} cores"

        return resource_str
